"""M8 CSV/XLSX 导入中心：预览和确认提交严格分离。"""

import csv
import io
import secrets
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated
from zipfile import BadZipFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import SessionDep, get_current_user, get_workspace_access
from app.models import BusinessMetric, ImportBatch, Product, ProductSku, Store, User
from app.schemas.imports import ImportCommit, ImportPreviewRead
from app.services.audit import record_audit_event
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/imports", tags=["imports"])
Access = Annotated[WorkspaceAccess, Depends(get_workspace_access)]
TEMPLATES = {
    "products": [
        "store_id",
        "name",
        "category",
        "description",
        "platform_item_code",
        "cost",
        "target_audience",
        "selling_points",
    ],
    "skus": ["product_id", "sku_code", "specification", "price", "stock", "warning_threshold"],
    "metrics": [
        "product_id",
        "period_start",
        "period_end",
        "source",
        "target_gmv",
        "actual_gmv",
        "target_impressions",
        "actual_impressions",
        "target_ctr",
        "actual_ctr",
        "target_conversion_rate",
        "actual_conversion_rate",
        "target_roi",
        "actual_roi",
    ],
}
UPLOAD_FILE = File(...)


def _parse(data: bytes, filename: str, data_type: str) -> list[tuple[int, dict]]:
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "导入文件不能超过 5 MB")
    if not filename.lower().endswith((".csv", ".xlsx")):
        raise HTTPException(422, "仅支持 CSV 或 XLSX 文件")
    if filename.lower().endswith(".xlsx"):
        try:
            from openpyxl import load_workbook

            sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
            rows = list(sheet.values)
            if not rows:
                raise HTTPException(422, "文件中没有表头，请使用下载的导入模板")
            headers = [str(v or "").strip() for v in rows[0]]
            parsed_rows: list[tuple[int, dict]] = []
            for line_number, row in enumerate(rows[1:], start=2):
                if not any(value is not None for value in row):
                    continue
                parsed = dict(zip(headers, row, strict=False))
                if any(value is not None for value in row[len(headers) :]):
                    parsed["__extra_columns__"] = True
                parsed_rows.append((line_number, parsed))
        except (ImportError, ValueError, IndexError, KeyError, OSError, BadZipFile) as exc:
            raise HTTPException(422, "Excel 文件无法解析") from exc
        _validate_headers(headers, data_type)
        if not parsed_rows:
            raise HTTPException(422, "文件中没有可导入的数据行")
        return parsed_rows
    try:
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
        _validate_headers(headers, data_type)
        parsed_rows: list[tuple[int, dict]] = []
        for row in reader:
            line_number = reader.line_num
            if not any(str(value or "").strip() for value in row.values()):
                continue
            if None in row:
                row["__extra_columns__"] = any(str(value or "").strip() for value in row.pop(None))
            parsed_rows.append((line_number, row))
        if not parsed_rows:
            raise HTTPException(422, "文件中没有可导入的数据行")
        return parsed_rows
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "CSV 必须使用 UTF-8 编码") from exc


def _validate_headers(headers: list[str], data_type: str) -> None:
    expected = TEMPLATES[data_type]
    if not headers or any(not header for header in headers):
        raise HTTPException(422, "模板表头不能为空，请使用下载的导入模板")
    if len(headers) != len(set(headers)):
        raise HTTPException(422, "模板中存在重复字段，请使用下载的导入模板")
    missing = [field for field in expected if field not in headers]
    unknown = [field for field in headers if field not in expected]
    if missing or unknown:
        details = []
        if missing:
            details.append(f"缺少字段：{', '.join(missing)}")
        if unknown:
            details.append(f"未知字段：{', '.join(unknown)}")
        raise HTTPException(422, f"模板表头与{data_type}模板不匹配（{'；'.join(details)}）")


def _validate(data_type: str, row: dict, number: int, db, access) -> dict:
    errors = []
    if row.get("__extra_columns__"):
        errors.append("该行包含模板之外的额外列数据")
    fields = TEMPLATES[data_type]
    normalized = {field: row.get(field) for field in fields}
    for field in fields:
        if field not in row:
            errors.append(f"缺少字段 {field}")
    for field in ("name", "sku_code", "specification", "period_start", "period_end"):
        if field in fields and not str(normalized.get(field) or "").strip():
            errors.append(f"{field} 不能为空")
    try:
        if data_type == "products":
            store = db.get(Store, int(normalized["store_id"]))
            if store is None or store.workspace_id != access.workspace.id:
                errors.append("store_id 不属于当前工作空间")
            if normalized.get("cost") not in (None, "") and Decimal(str(normalized["cost"])) < 0:
                errors.append("cost 不能为负数")
        elif data_type == "skus":
            product = db.get(Product, int(normalized["product_id"]))
            if (
                product is None
                or (store := db.get(Store, product.store_id)) is None
                or store.workspace_id != access.workspace.id
            ):
                errors.append("product_id 不属于当前工作空间")
            if Decimal(str(normalized["price"])) < 0:
                errors.append("price 不能为负数")
            for field in ("stock", "warning_threshold"):
                value = Decimal(str(normalized[field]))
                if value < 0 or value != value.to_integral_value():
                    errors.append(f"{field} 必须为非负整数")
        else:
            product = db.get(Product, int(normalized["product_id"]))
            if (
                product is None
                or (store := db.get(Store, product.store_id)) is None
                or store.workspace_id != access.workspace.id
            ):
                errors.append("product_id 不属于当前工作空间")
            start = date.fromisoformat(str(normalized["period_start"]))
            end = date.fromisoformat(str(normalized["period_end"]))
            if end < start:
                errors.append("period_end 不能早于 period_start")
            if not str(normalized.get("source") or "").strip():
                errors.append("source 不能为空")
            for field in fields[4:]:
                value = Decimal(str(normalized[field]))
                if value < 0:
                    errors.append(f"{field} 不能为负数")
                if "impressions" in field and value != value.to_integral_value():
                    errors.append(f"{field} 必须为非负整数")
                if "rate" in field or "ctr" in field:
                    if value < 0 or value > 1:
                        errors.append(f"{field} 必须在 0 到 1 之间")
    except (ValueError, TypeError, InvalidOperation):
        errors.append("数值或日期格式不合法")
    return {"line": number, "data": normalized, "valid": not errors, "errors": errors}


@router.get("/templates/{data_type}")
def template(
    data_type: str,
    _user: Annotated[User, Depends(get_current_user)],
    file_format: str = "csv",
):
    if data_type not in TEMPLATES:
        raise HTTPException(404, "模板类型不存在")
    if file_format not in {"csv", "xlsx"}:
        raise HTTPException(422, "模板格式仅支持 CSV 或 XLSX")
    if file_format == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "导入模板"
        headers = TEMPLATES[data_type]
        sheet.append(headers)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="137B6D")
        for index, header in enumerate(headers, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = min(
                max(len(header) + 4, 16), 30
            )
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{data_type}-template.xlsx"'},
        )
    body = io.StringIO(newline="")
    csv.writer(body).writerow(TEMPLATES[data_type])
    return StreamingResponse(
        iter([body.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{data_type}-template.csv"'},
    )


@router.get("/batches", response_model=list[ImportPreviewRead])
def list_batches(db: SessionDep, access: Access):
    """返回当前工作空间的导入历史，供工作台复查批次状态。"""
    return list(
        db.scalars(
            select(ImportBatch)
            .where(ImportBatch.workspace_id == access.workspace.id)
            .order_by(ImportBatch.created_at.desc())
            .limit(50)
        )
    )


@router.post("/preview", response_model=ImportPreviewRead, status_code=201)
async def preview(data_type: str, db: SessionDep, access: Access, file: UploadFile = UPLOAD_FILE):
    if data_type not in TEMPLATES:
        raise HTTPException(422, "不支持的导入类型")
    contents = await file.read(5 * 1024 * 1024 + 1)
    rows = [
        _validate(data_type, row, line_number, db, access)
        for line_number, row in _parse(contents, file.filename or "upload.csv", data_type)
    ]
    batch = ImportBatch(
        workspace_id=access.workspace.id,
        batch_key=secrets.token_urlsafe(18),
        data_type=data_type,
        filename=file.filename or "upload.csv",
        rows=rows,
        valid_count=sum(r["valid"] for r in rows),
        error_count=sum(not r["valid"] for r in rows),
        created_by=access.user.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.post("/{batch_id}/commit", response_model=ImportPreviewRead)
def commit(batch_id: int, payload: ImportCommit, db: SessionDep, access: Access):
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "导入批次不存在")
    if batch.workspace_id != access.workspace.id:
        raise HTTPException(403, "无权访问此批次")
    if batch.status != "preview" or batch.version != payload.version:
        raise HTTPException(409, "批次已提交或版本已过期")
    for row in batch.rows:
        if not row["valid"]:
            continue
        data = row["data"]
        if batch.data_type == "products":
            db.add(
                Product(
                    store_id=int(data["store_id"]),
                    name=str(data["name"]),
                    category=str(data.get("category") or ""),
                    description=str(data.get("description") or ""),
                    platform_item_code=str(data.get("platform_item_code") or ""),
                    cost=Decimal(str(data["cost"])) if data.get("cost") else None,
                    target_audience=str(data.get("target_audience") or ""),
                    selling_points=str(data.get("selling_points") or ""),
                )
            )
        elif batch.data_type == "skus":
            db.add(
                ProductSku(
                    product_id=int(data["product_id"]),
                    sku_code=str(data["sku_code"]),
                    specification=str(data["specification"]),
                    price=Decimal(str(data["price"])),
                    stock=int(data["stock"]),
                    warning_threshold=int(data["warning_threshold"]),
                )
            )
        else:
            db.add(
                BusinessMetric(
                    workspace_id=access.workspace.id,
                    product_id=int(data["product_id"]),
                    period_start=date.fromisoformat(str(data["period_start"])),
                    period_end=date.fromisoformat(str(data["period_end"])),
                    source=str(data["source"]),
                    target_gmv=Decimal(str(data["target_gmv"])),
                    actual_gmv=Decimal(str(data["actual_gmv"])),
                    target_impressions=int(data["target_impressions"]),
                    actual_impressions=int(data["actual_impressions"]),
                    target_ctr=Decimal(str(data["target_ctr"])),
                    actual_ctr=Decimal(str(data["actual_ctr"])),
                    target_conversion_rate=Decimal(str(data["target_conversion_rate"])),
                    actual_conversion_rate=Decimal(str(data["actual_conversion_rate"])),
                    target_roi=Decimal(str(data["target_roi"])),
                    actual_roi=Decimal(str(data["actual_roi"])),
                    created_by=access.user.id,
                )
            )
    batch.status = "committed"
    batch.version += 1
    batch.committed_at = datetime.now(UTC)
    record_audit_event(
        db,
        access=access,
        action="import.commit",
        resource_type="import_batch",
        resource_id=str(batch.id),
        details={"valid_count": batch.valid_count, "error_count": batch.error_count},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "导入数据与已有记录重复，请修正后重新预览") from exc
    db.refresh(batch)
    return batch
