"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowDownWideNarrow, ArrowUpRight, RefreshCw } from "lucide-react";
import { api, type Reading, type ReadingSource, type ReadingStatus, type Severity } from "@/lib/api";
import { usePollingInterval } from "@/lib/settings";

const filters = [{ label: "Today", days: 1 }, { label: "7 days", days: 7 }, { label: "30 days", days: 30 }, { label: "All time", days: undefined }];

export default function AnomaliesPage() {
  const [rows, setRows] = useState<Reading[]>([]);
  const [days, setDays] = useState<number | undefined>(7);
  const [source, setSource] = useState<ReadingSource>("wokwi_simulation");
  const pollingInterval = usePollingInterval();
  const [status, setStatus] = useState<ReadingStatus | "all">("ANOMALY");
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [sort, setSort] = useState<"recent" | "score">("recent");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = async (range = days) => {
    setLoading(true);
    try { setRows(await api.readings(1000, source, status === "all" ? undefined : status, range)); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load anomaly history."); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    let active = true;
    const refresh = () => {
      api.readings(1000, source, status === "all" ? undefined : status, days).then((result) => { if (active) { setRows(result); setError(""); } })
        .catch((reason: Error) => { if (active) setError(reason.message); })
        .finally(() => { if (active) setLoading(false); });
    };
    refresh();
    const timer = window.setInterval(refresh, pollingInterval * 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [days, source, status, pollingInterval]);
  const sortedRows = useMemo(() => [...rows]
    .filter((row) => severity === "all" || row.severity === severity)
    .sort((a, b) => sort === "score" ? b.anomaly_score - a.anomaly_score : b.timestamp.localeCompare(a.timestamp)), [rows, sort, severity]);

  return <>
    <div className="page-heading"><div><div className="eyebrow">EVENT REVIEW <span>·</span> RECONSTRUCTION ERROR</div><h1>Anomaly <em>history</em></h1><p>Abnormal energy patterns flagged against the learned normal-load profile.</p></div><button className="icon-button" onClick={() => void load()} title="Refresh anomalies" aria-label="Refresh anomalies"><RefreshCw size={16} /></button></div>
    {error && <div className="inline-alert error-alert"><span>{error}</span><button className="text-button" onClick={() => void load()}>Retry</button></div>}
    <div className="filter-row"><div className="filter-controls"><div className="segmented-control" role="group" aria-label="Filter by date">{filters.map((filter) => <button key={filter.label} className={days === filter.days ? "selected" : ""} onClick={() => setDays(filter.days)}>{filter.label}</button>)}</div><label className="source-picker source-picker-compact"><span>SOURCE</span><select value={source} onChange={(event) => setSource(event.target.value as ReadingSource)} aria-label="Reading source"><option value="wokwi_simulation">Wokwi simulation</option><option value="live">Other live sensor</option><option value="campus">Authorized campus data</option><option value="public_dataset">Public dataset</option><option value="demo">Generated demo data</option></select></label><label className="source-picker source-picker-compact"><span>STATUS</span><select value={status} onChange={(event) => setStatus(event.target.value as ReadingStatus | "all")} aria-label="Filter reading status"><option value="ANOMALY">Anomalies</option><option value="NORMAL">Normal</option><option value="all">All readings</option></select></label><label className="source-picker source-picker-compact"><span>SEVERITY</span><select value={severity} onChange={(event) => setSeverity(event.target.value as Severity | "all")} aria-label="Filter anomaly severity"><option value="all">All levels</option><option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option><option value="CRITICAL">Critical</option></select></label></div><button className="sort-button" onClick={() => setSort(sort === "score" ? "recent" : "score")}><ArrowDownWideNarrow size={15} /> Sort: {sort === "score" ? "highest score" : "most recent"}</button></div>
    <section className="panel anomaly-table-panel"><div className="table-summary"><span><strong>{sortedRows.length}</strong> matching readings</span><span>Showing {days ? `last ${days} days` : "all stored history"}</span></div>
      {loading ? <div className="table-empty">Loading energy history…</div> : sortedRows.length ? <div className="table-scroll"><table><thead><tr><th>TIMESTAMP</th><th>VOLTAGE</th><th>CURRENT</th><th>POWER</th><th>ENERGY</th><th>ERROR SCORE</th><th>THRESHOLD</th><th>STATUS</th><th>SEVERITY</th></tr></thead><tbody>{sortedRows.map((row) => <tr key={row.id}><td>{new Date(row.timestamp).toLocaleString()}</td><td>{row.voltage.toFixed(1)} V</td><td>{row.current.toFixed(2)} A</td><td>{row.power.toFixed(1)} W</td><td>{row.energy.toFixed(5)} kWh</td><td className="score-cell">{row.anomaly_score.toFixed(6)}</td><td>{row.threshold.toFixed(6)}</td><td><span className={`table-status ${row.status === "ANOMALY" ? "status-bad" : "status-good"}`}>{row.status}</span></td><td><span className={`severity severity-${row.severity.toLowerCase()}`}>{row.severity}</span></td></tr>)}</tbody></table></div> : <div className="empty-state"><span className="empty-icon">✓</span><strong>No readings match these filters</strong><p>Stored readings appear here with the selected source, status, severity, and date range.</p><Link href="/">Return to dashboard <ArrowUpRight size={14} /></Link></div>}
    </section>
    <div className="note-line">An anomaly signals an unusual pattern in the provided features; it does not identify a specific equipment fault.</div>
  </>;
}