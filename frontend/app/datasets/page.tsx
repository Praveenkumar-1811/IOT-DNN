"use client";

import { useEffect, useState } from "react";
import { FileUp, RefreshCw } from "lucide-react";
import { api, readingSourceLabel, type DatasetImport, type ImportReport, type ReadingSource } from "@/lib/api";

const aliases: Record<string, string> = { datetime: "timestamp", date: "timestamp", amps: "current", volts: "voltage", watts: "power" };

export default function DatasetsPage() {
  const [source, setSource] = useState<Exclude<ReadingSource, "live" | "wokwi_simulation">>("campus");
  const [file, setFile] = useState<File | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [preview, setPreview] = useState<string[]>([]);
  const [imports, setImports] = useState<DatasetImport[]>([]);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = async () => setImports(await api.datasets());
  useEffect(() => {
    let active = true;
    api.datasets().then((items) => { if (active) setImports(items); }).catch((reason: Error) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, []);

  const selectFile = async (selected?: File) => {
    setFile(selected ?? null);
    setReport(null);
    if (!selected) {
      setColumns([]);
      setPreview([]);
      return;
    }
    const text = await selected.text();
    const lines = text.split(/\r?\n/).filter(Boolean);
    const header = (lines[0] ?? "").split(",").map((column) => column.trim().replace(/^"|"$/g, "").toLowerCase());
    setColumns(header);
    setPreview(lines.slice(0, 6));
  };

  const normalizedColumns = columns.map((column) => aliases[column] ?? column);
  const missingRequired = ["timestamp", "voltage", "current"].filter((column) => !normalizedColumns.includes(column));

  const importFile = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      setReport(await api.upload(file, source));
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "CSV import failed.");
    } finally {
      setBusy(false);
    }
  };

  return <>
    <div className="page-heading"><div><div className="eyebrow">DATA PROVENANCE <span>·</span> CSV IMPORTS</div><h1>Dataset <em>management</em></h1><p>Preview, validate, and import records without replacing existing data or model artifacts.</p></div><button className="icon-button" onClick={() => void refresh()} aria-label="Refresh import history"><RefreshCw size={16} /></button></div>
    {error && <div className="inline-alert error-alert">{error}</div>}
    <section className="panel dataset-import-panel">
      <div className="panel-heading"><div><span className="panel-kicker">NEW IMPORT</span><h2>Upload a CSV file</h2></div></div>
      <p className="settings-description">Campus imports must be authorized. Public and derived BDG2 data must remain labelled as public_dataset. The required inputs are timestamp, voltage, and current; missing power is derived and missing interval energy uses the documented five-second estimate.</p>
      <div className="import-controls">
        <label className="source-picker"><span>STORE AS</span><select value={source} onChange={(event) => setSource(event.target.value as Exclude<ReadingSource, "live" | "wokwi_simulation">)}><option value="campus">Authorized campus data</option><option value="public_dataset">Public dataset</option><option value="demo">Generated demo data</option></select></label>
        <label className="upload-button"><FileUp size={16} />{file?.name ?? "Choose CSV"}<input type="file" accept=".csv,text/csv" onChange={(event) => void selectFile(event.target.files?.[0])} /></label>
        <button className="small-action" disabled={!file || missingRequired.length > 0 || busy} onClick={() => void importFile()}>{busy ? "Importing…" : "Validate and import"}</button>
      </div>
      {file && <div className="dataset-preview"><h3>Preview · {file.name} · {file.size.toLocaleString()} bytes</h3><p>{missingRequired.length ? `Missing required columns: ${missingRequired.join(", ")}` : "Required columns found. Row-level errors and duplicate timestamps will be reported."}</p><div className="table-scroll"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{preview.slice(1).map((line, index) => <tr key={`${line}-${index}`}>{line.split(",").map((value, cellIndex) => <td key={cellIndex}>{value.replace(/^"|"$/g, "")}</td>)}</tr>)}</tbody></table></div></div>}
    </section>
    {report && <section className="panel import-report"><div className="panel-heading"><div><span className="panel-kicker">IMPORT #{report.id}</span><h2>{report.filename}</h2></div><span className="chart-unit">{report.source}</span></div><div className="metric-grid import-counts"><article><small>TOTAL ROWS</small><strong>{report.total_rows}</strong></article><article><small>IMPORTED</small><strong>{report.accepted_rows}</strong></article><article><small>REJECTED</small><strong>{report.rejected_rows}</strong></article><article><small>DUPLICATES</small><strong>{report.duplicate_rows}</strong></article></div>{report.errors.length > 0 && <div className="table-scroll"><table><thead><tr><th>CSV ROW</th><th>RESULT</th></tr></thead><tbody>{report.errors.map((item, index) => <tr key={`${item.row}-${index}`}><td>{item.row}</td><td>{item.error}</td></tr>)}</tbody></table></div>}</section>}
    <section className="panel latest-panel"><div className="panel-heading"><div><span className="panel-kicker">IMPORT LOG</span><h2>Dataset provenance history</h2></div><span className="chart-unit">{imports.length} RECENT IMPORTS</span></div>
      {imports.length ? <div className="table-scroll"><table><thead><tr><th>IMPORTED</th><th>FILE</th><th>SOURCE</th><th>TOTAL</th><th>ACCEPTED</th><th>REJECTED</th><th>DUPLICATES</th><th>IMPORT ID</th></tr></thead><tbody>{imports.map((item) => <tr key={item.id}><td>{new Date(item.imported_at).toLocaleString()}</td><td>{item.filename}</td><td>{readingSourceLabel(item.source)}</td><td>{item.total_rows}</td><td>{item.accepted_rows}</td><td>{item.rejected_rows}</td><td>{item.duplicate_rows}</td><td>{item.id}</td></tr>)}</tbody></table></div> : <div className="table-empty">No dataset imports have been recorded.</div>}
    </section>
  </>;
}
