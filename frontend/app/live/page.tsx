"use client";

import { useEffect, useState } from "react";
import { api, readingSourceLabel, type Reading, type ReadingSource } from "@/lib/api";
import { usePollingInterval } from "@/lib/settings";

export default function LiveMonitoringPage() {
  const [source, setSource] = useState<ReadingSource>("wokwi_simulation");
  const [latest, setLatest] = useState<Reading | null>(null);
  const [rows, setRows] = useState<Reading[]>([]);
  const [error, setError] = useState("");
  const interval = usePollingInterval();
  useEffect(() => {
    let active = true;
    const refresh = () => Promise.all([api.latest(source), api.readings(25, source)])
      .then(([reading, recent]) => { if (active) { setLatest(reading); setRows(recent); setError(""); } })
      .catch((reason: Error) => { if (active) setError(reason.message); });
    void refresh();
    const timer = window.setInterval(() => void refresh(), interval * 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [source, interval]);
  return <>
    <div className="page-heading"><div><div className="eyebrow">PERIODIC API POLLING <span>·</span> NO SYNTHETIC CLIENT DATA</div><h1>Live <em>monitoring</em></h1><p>Latest persisted reading for the selected source, refreshed every {interval} seconds.</p></div><label className="source-picker"><span>SOURCE</span><select value={source} onChange={(event) => setSource(event.target.value as ReadingSource)}><option value="wokwi_simulation">Wokwi simulation</option><option value="live">Other live sensor</option><option value="demo">Generated demo data</option><option value="public_dataset">Public dataset</option><option value="campus">Authorized campus measurement</option></select></label></div>
    {error && <div className="inline-alert error-alert">{error}<button className="text-button" onClick={() => window.location.reload()}>Retry</button></div>}
    {latest ? <><section className="metric-grid"><article className="metric-card"><div className="metric-heading">LATEST POWER</div><div className="metric-value">{latest.power.toFixed(1)}<small>W</small></div><div className="metric-detail">{new Date(latest.timestamp).toLocaleString()}</div></article><article className="metric-card"><div className="metric-heading">VOLTAGE</div><div className="metric-value">{latest.voltage.toFixed(1)}<small>V</small></div></article><article className="metric-card"><div className="metric-heading">CURRENT</div><div className="metric-value">{latest.current.toFixed(2)}<small>A</small></div></article><article className="metric-card"><div className="metric-heading">INTERVAL ENERGY</div><div className="metric-value">{latest.interval_energy_kwh.toFixed(6)}<small>kWh</small></div></article></section><section className="status-strip"><div className={`reading-state ${latest.status === "ANOMALY" ? "state-anomaly" : "state-normal"}`}><span className="state-symbol">{latest.status === "ANOMALY" ? "!" : "✓"}</span><div><small>MODEL CLASSIFICATION</small><strong>{latest.status}</strong></div></div><div className="status-stat"><small>DATA PROVENANCE</small><strong>{readingSourceLabel(latest.source)}</strong></div><div className="status-stat"><small>DEVICE / LAST SEEN</small><strong>{latest.device_id ?? "No device ID"} · {new Date(latest.timestamp).toLocaleTimeString()}</strong></div><div className="status-stat"><small>SCORE / THRESHOLD</small><strong>{latest.anomaly_score.toFixed(6)} / {latest.threshold.toFixed(6)}</strong></div><div className="status-stat"><small>DEVIATION LEVEL</small><strong>{latest.severity}</strong></div></section></> : <div className="empty-banner">{error ? "Backend unavailable. No live readings are fabricated; reconnect to the API and retry." : `No stored reading is available for ${readingSourceLabel(source)}.`}</div>}
    <section className="panel latest-panel"><div className="panel-heading"><div><span className="panel-kicker">RECENT RECORDS</span><h2>Latest 25 readings</h2></div></div>{rows.length ? <div className="table-scroll"><table><thead><tr><th>TIMESTAMP</th><th>POWER</th><th>VOLTAGE</th><th>CURRENT</th><th>ENERGY</th><th>SCORE</th><th>THRESHOLD</th><th>STATUS</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{new Date(row.timestamp).toLocaleString()}</td><td>{row.power.toFixed(1)} W</td><td>{row.voltage.toFixed(1)} V</td><td>{row.current.toFixed(2)} A</td><td>{row.energy.toFixed(6)} kWh</td><td>{row.anomaly_score.toFixed(6)}</td><td>{row.threshold.toFixed(6)}</td><td>{row.status}</td></tr>)}</tbody></table></div> : <div className="table-empty">No readings stored for this source.</div>}</section>
    <p className="note-line">{source === "wokwi_simulation" ? "Wokwi values are simulated sensor readings, not physical electrical measurements. " : ""}Polling fetches existing API records only. It does not create readings. Severity is a model-derived deviation, not a confirmed electrical fault.</p>
  </>;
}
