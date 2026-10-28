"use client";

import { useEffect, useState } from "react";
import { Download, ChevronLeft, ChevronRight } from "lucide-react";
import { api, readingSourceLabel, type Reading, type ReadingSource, type ReadingStatus } from "@/lib/api";

const PAGE_SIZE = 25;

function downloadCsv(rows: Reading[]) {
  const columns: (keyof Reading)[] = [
    "timestamp", "source", "voltage", "current", "power", "energy",
    "anomaly_score", "threshold", "status", "severity", "model_version", "import_id",
  ];
  const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const content = [columns.join(","), ...rows.map((row) => columns.map((column) => escape(row[column])).join(","))].join("\r\n");
  const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "energy-readings-page.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function HistoryPage() {
  const [rows, setRows] = useState<Reading[]>([]);
  const [source, setSource] = useState<ReadingSource | "all">("all");
  const [status, setStatus] = useState<ReadingStatus | "all">("all");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const since = fromDate ? new Date(`${fromDate}T00:00:00.000Z`).toISOString() : undefined;
  const until = toDate ? new Date(`${toDate}T23:59:59.999Z`).toISOString() : undefined;

  useEffect(() => {
    let active = true;
    Promise.all([
      api.readings(PAGE_SIZE, source === "all" ? undefined : source, status === "all" ? undefined : status, undefined, page * PAGE_SIZE, since, until),
      api.count(source === "all" ? undefined : source, status === "all" ? undefined : status, since, until),
    ]).then(([readings, count]) => {
      if (active) {
        setRows(readings);
        setTotal(count.count);
        setError("");
      }
    }).catch((reason: Error) => {
      if (active) setError(reason.message);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [source, status, since, until, page]);

  const changeFilter = (change: () => void) => {
    setLoading(true);
    change();
    setPage(0);
  };

  return <>
    <div className="page-heading"><div><div className="eyebrow">PERSISTED RECORDS <span>·</span> SQLITE</div><h1>Reading <em>history</em></h1><p>Filter stored observations and export the currently displayed page.</p></div>
      <button className="small-action" onClick={() => downloadCsv(rows)} disabled={!rows.length}><Download size={15} /> Export this page</button>
    </div>
    {error && <div className="inline-alert error-alert">{error}</div>}
    <div className="filter-row"><div className="filter-controls">
      <label className="source-picker"><span>SOURCE</span><select value={source} onChange={(event) => changeFilter(() => setSource(event.target.value as ReadingSource | "all"))}><option value="all">All sources</option><option value="wokwi_simulation">Wokwi simulation</option><option value="live">Other live sensor</option><option value="demo">Generated demo</option><option value="public_dataset">Public dataset</option><option value="campus">Authorized campus</option></select></label>
      <label className="source-picker"><span>STATUS</span><select value={status} onChange={(event) => changeFilter(() => setStatus(event.target.value as ReadingStatus | "all"))}><option value="all">All statuses</option><option value="NORMAL">Normal</option><option value="ANOMALY">Anomaly</option></select></label>
      <label className="source-picker"><span>FROM (UTC)</span><input type="date" value={fromDate} onChange={(event) => changeFilter(() => setFromDate(event.target.value))} /></label>
      <label className="source-picker"><span>TO (UTC)</span><input type="date" value={toDate} onChange={(event) => changeFilter(() => setToDate(event.target.value))} /></label>
    </div></div>
    <section className="panel anomaly-table-panel">
      <div className="table-summary"><span><strong>{total}</strong> matching readings</span><span>Page {page + 1} · {PAGE_SIZE} per page</span></div>
      {loading ? <div className="table-empty">Loading reading history…</div> : rows.length ? <div className="table-scroll"><table><thead><tr><th>TIMESTAMP</th><th>SOURCE</th><th>VOLTAGE</th><th>CURRENT</th><th>POWER</th><th>ENERGY</th><th>SCORE / THRESHOLD</th><th>STATUS</th><th>MODEL VERSION</th><th>IMPORT</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{new Date(row.timestamp).toLocaleString()}</td><td>{readingSourceLabel(row.source)}</td><td>{row.voltage.toFixed(1)} V</td><td>{row.current.toFixed(2)} A</td><td>{row.power.toFixed(1)} W</td><td>{row.interval_energy_kwh.toFixed(6)} kWh</td><td>{row.anomaly_score.toFixed(5)} / {row.threshold.toFixed(5)}</td><td><span className={`table-status ${row.status === "ANOMALY" ? "status-bad" : "status-good"}`}>{row.status}</span></td><td>{row.model_version}</td><td>{row.import_id ?? "—"}</td></tr>)}</tbody></table></div> : <div className="table-empty">No readings match these filters.</div>}
      <div className="history-pagination"><button className="icon-button" aria-label="Previous page" disabled={page === 0 || loading} onClick={() => { setLoading(true); setPage((current) => current - 1); }}><ChevronLeft size={16} /></button><span>{total ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} of ${total}` : "0 records"}</span><button className="icon-button" aria-label="Next page" disabled={(page + 1) * PAGE_SIZE >= total || loading} onClick={() => { setLoading(true); setPage((current) => current + 1); }}><ChevronRight size={16} /></button></div>
    </section>
  </>;
}
