"use client";

import { useCallback, useEffect, useState, type ChangeEvent } from "react";
import { UiSelect, type SelectOption } from "@/components/ui-select";
import { importRequest, type ImportPreview } from "@/lib/imports";

type DataType = "products" | "skus" | "metrics";
type FileFormat = "csv" | "xlsx";

const typeOptions: SelectOption[] = [
  { value: "products", label: "商品" },
  { value: "skus", label: "SKU / 库存" },
  { value: "metrics", label: "经营数据" },
];
const typeLabels: Record<DataType, string> = { products: "商品", skus: "SKU / 库存", metrics: "经营数据" };

export function ImportWorkbench({ workspaceId }: { workspaceId: number }) {
  const [type, setType] = useState<DataType>("products");
  const [format, setFormat] = useState<FileFormat>("xlsx");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [history, setHistory] = useState<ImportPreview[]>([]);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await importRequest<ImportPreview[]>("batches", workspaceId));
      setHistoryError("");
    } catch (cause) {
      setHistoryError(cause instanceof Error ? cause.message : "导入记录加载失败");
    }
  }, [workspaceId]);

  useEffect(() => {
    let active = true;
    void importRequest<ImportPreview[]>("batches", workspaceId)
      .then((items) => { if (active) setHistory(items); })
      .catch((cause: unknown) => {
        if (active) setHistoryError(cause instanceof Error ? cause.message : "导入记录加载失败");
      });
    return () => { active = false; };
  }, [workspaceId]);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    setError("");
    try {
      const batch = await importRequest<ImportPreview>(`preview?data_type=${type}`, workspaceId, { method: "POST", body: form });
      setPreview(batch);
      await loadHistory();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "文件预览失败");
    } finally {
      setBusy(false);
      input.value = "";
    }
  }

  async function commit() {
    if (!preview || preview.status !== "preview" || preview.valid_count < 1 || busy) return;
    setBusy(true);
    setError("");
    try {
      const committed = await importRequest<ImportPreview>(`${preview.id}/commit`, workspaceId, {
        method: "POST",
        body: JSON.stringify({ version: preview.version }),
        headers: { "Content-Type": "application/json" },
      });
      setPreview(committed);
      await loadHistory();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "导入提交失败");
    } finally {
      setBusy(false);
    }
  }

  const filteredHistory = history.filter((item) => item.data_type === type);
  const templateHref = `/api/imports/templates/${type}?file_format=${format}`;
  const uploadButton = (
    <label className={`button primary ${busy ? "disabled" : ""}`}>
      {busy ? "正在处理…" : "＋ 选择文件"}
      <input hidden type="file" accept=".csv,.xlsx" disabled={busy} onChange={upload} />
    </label>
  );

  return <>
    <div className="page-heading">
      <div><p className="eyebrow">IMPORT CENTER</p><h1>批量导入中心</h1><p>下载 CSV 或 Excel 模板，上传后先预览校验，再明确确认写入。</p></div>
      <div className="import-actions">
        <div className="import-template-controls">
          <UiSelect className="import-type-select" value={type} options={typeOptions} onChange={(value) => { setType(value as DataType); setPreview(null); setError(""); }} ariaLabel="导入数据类型" disabled={busy} />
          <div className="format-toggle" role="group" aria-label="模板文件格式">
            <button type="button" className={format === "xlsx" ? "selected" : ""} aria-pressed={format === "xlsx"} onClick={() => setFormat("xlsx")} disabled={busy}>Excel (.xlsx)</button>
            <button type="button" className={format === "csv" ? "selected" : ""} aria-pressed={format === "csv"} onClick={() => setFormat("csv")} disabled={busy}>CSV (.csv)</button>
          </div>
          <a className="button secondary" href={templateHref}>↓ 下载{typeLabels[type]}模板</a>
        </div>
        {uploadButton}
      </div>
    </div>
    {error && <p className="notice error" role="alert">{error}</p>}
    <section className="import-steps panel" aria-label="导入流程"><div className="import-step active"><span>1</span><div><strong>下载并填写模板</strong><small>选择数据类型与文件格式</small></div></div><i aria-hidden="true">→</i><div className="import-step"><span>2</span><div><strong>预览与校验</strong><small>逐行查看字段和错误原因</small></div></div><i aria-hidden="true">→</i><div className="import-step"><span>3</span><div><strong>确认导入</strong><small>仅写入有效行，可追溯批次</small></div></div></section>
    <section className="metric-grid import-metrics" aria-label="导入概览"><div className="metric-card"><span>当前数据类型</span><strong className="metric-text">{typeLabels[type]}</strong><small>模板格式：{format === "xlsx" ? "Excel (.xlsx)" : "CSV (.csv)"}</small></div><div className="metric-card"><span>最近批次</span><strong>{filteredHistory.length}</strong><small>当前类型的历史记录</small></div><div className="metric-card"><span>待确认行数</span><strong>{preview?.status === "preview" ? preview.valid_count : 0}</strong><small>预览批次中的有效行</small></div><div className="metric-card warning"><span>待处理错误</span><strong>{preview?.status === "preview" ? preview.error_count : 0}</strong><small>需修正后重新上传</small></div></section>
    <div className="import-layout">
      <section className="panel import-main" aria-label="导入预览">
        <div className="section-heading"><div><h2>导入预览</h2><p className="subtle">预览阶段不会修改商品、库存或经营数据。</p></div><span className="muted-tag">{typeLabels[type]}数据</span></div>
        {!preview ? <div className="import-empty"><span className="empty-icon">↥</span><h3>{busy ? "正在校验文件" : "还没有预览批次"}</h3><p>{busy ? "请保持页面打开，校验完成后会显示逐行结果。" : "下载对应模板并填写数据，上传后系统会逐行检查字段与内容。"}</p>{uploadButton}</div> : <>
          <div className="import-batch-summary"><div><span>当前批次</span><strong>#{preview.id} · {preview.filename}</strong></div><span className={`status-badge ${preview.status === "committed" ? "ok" : ""}`}><i className="status-dot" />{preview.status === "committed" ? "已完成" : "待确认"}</span></div>
          {preview.status === "preview" && <p className="import-validation-note">确认后仅导入有效行，{preview.error_count ? `${preview.error_count} 行错误数据会保留在批次记录中，不写入业务表。` : "当前文件所有数据行均通过校验。"}</p>}
          <div className="list-table import-table"><div className="table-head"><span>行号</span><span>校验状态</span><span>字段预览</span><span>反馈</span></div>{preview.rows.map((row) => <div className="table-row" key={row.line}><span>第 {row.line} 行</span><strong className={row.valid ? "import-valid" : "import-invalid"}>{row.valid ? "有效" : "错误"}</strong><code>{JSON.stringify(row.data)}</code><span>{row.valid ? "可导入" : row.errors.join("；")}</span></div>)}</div>
          {preview.status === "preview" && <div className="import-confirm"><span>有效 {preview.valid_count} 行，错误 {preview.error_count} 行</span><button type="button" className="button primary" disabled={busy || !preview.valid_count} onClick={commit}>{busy ? "正在导入…" : `确认导入 ${preview.valid_count} 行`}</button></div>}
        </>}
      </section>
      <aside className="import-rail">
        <section className="panel"><h2>导入说明</h2><ul className="import-tips"><li>可选择 CSV 或 Excel 两种模板，上传时两种格式均支持。</li><li>不要修改模板字段名称；日期使用 YYYY-MM-DD 格式。</li><li>预览发现错误时，修正文件后重新上传即可。</li><li>提交前会再次检查批次状态，避免重复导入。</li></ul></section>
        <section className="panel"><div className="section-heading"><h2>最近批次</h2><button type="button" className="text-action" onClick={() => void loadHistory()} disabled={busy}>刷新</button></div>
          {historyError && <p className="notice error" role="alert">{historyError}</p>}
          {filteredHistory.length ? <div className="import-history">{filteredHistory.slice(0, 5).map((item) => <button type="button" className="import-history-item" key={item.id} onClick={() => { setPreview(item); setError(""); }}><span><strong>#{item.id}</strong><small>{item.filename}</small></span><em>{item.status === "committed" ? "已完成" : `${item.valid_count} 行待确认`}</em></button>)}</div> : !historyError && <p className="subtle">当前类型还没有导入记录。</p>}
        </section>
      </aside>
    </div>
  </>;
}
