"""M8 CSV/XLSX 导入中心：预览和确认提交严格分离。"""

import csv
import io
import secrets
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.dependencies import SessionDep, get_workspace_access
from app.models import BusinessMetric, ImportBatch, Product, ProductSku, Store
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


def _parse(data: bytes, filename: str) -> list[dict]:
    if filename.lower().endswith(".xlsx"):
        try:
            from openpyxl import load_workbook

            sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
            rows = list(sheet.values)
            headers = [str(v or "").strip() for v in rows[0]]
            return [
                dict(zip(headers, row, strict=False))
                for row in rows[1:]
                if any(v is not None for v in row)
            ]
        except (ImportError, ValueError, IndexError) as exc:
            raise HTTPException(422, "Excel 文件无法解析") from exc
    try:
        text = data.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "CSV 必须使用 UTF-8 编码") from exc


def _validate(data_type: str, row: dict, number: int, db, access) -> dict:
    errors = []
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
            if normalized.get("cost") not in (None, ""):
                Decimal(str(normalized["cost"]))
        elif data_type == "skus":
            product = db.get(Product, int(normalized["product_id"]))
            if (
                product is None
                or db.get(Store, product.store_id).workspace_id != access.workspace.id
            ):
                errors.append("product_id 不属于当前工作空间")
            for field in ("price", "stock", "warning_threshold"):
                Decimal(str(normalized[field]))
        else:
            product = db.get(Product, int(normalized["product_id"]))
            if (
                product is None
                or db.get(Store, product.store_id).workspace_id != access.workspace.id
            ):
                errors.append("product_id 不属于当前工作空间")
            date.fromisoformat(str(normalized["period_start"]))
            date.fromisoformat(str(normalized["period_end"]))
            for field in fields[4:]:
                Decimal(str(normalized[field]))
    except (ValueError, TypeError, InvalidOperation):
        errors.append("数值或日期格式不合法")
    return {"line": number, "data": normalized, "valid": not errors, "errors": errors}


@router.get("/templates/{data_type}")
def template(data_type: str):
    if data_type not in TEMPLATES:
        raise HTTPException(404, "模板类型不存在")
    body = io.StringIO()
    csv.writer(body).writerow(TEMPLATES[data_type])
    return StreamingResponse(
        iter([body.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{data_type}-template.csv"'},
    )


@router.post("/preview", response_model=ImportPreviewRead, status_code=201)
async def preview(data_type: str, db: SessionDep, access: Access, file: UploadFile = UPLOAD_FILE):
    if data_type not in TEMPLATES:
        raise HTTPException(422, "不支持的导入类型")
    rows = [
        _validate(data_type, row, index, db, access)
        for index, row in enumerate(_parse(await file.read(), file.filename or "upload.csv"), 2)
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
    db.commit()
    db.refresh(batch)
    return batch
