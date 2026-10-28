"use client";

import { useEffect, useState } from "react";
import { api, readingSourceLabel, type Analytics, type ReadingSource } from "@/lib/api";
import { DailyEnergyChart } from "@/components/charts";
import { usePollingInterval } from "@/lib/settings";

function Metric({ label, value, unit }: { label: string; value: string; unit: string }) {
  return <article className="metric-card"><div className="metric-heading"><span>{label}</span><span className="metric-mark mint" /></div><div className="metric-value">{value}<small>{unit}</small></div><div className="metric-detail">Calculated from persisted readings</div></article>;
}

export default function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState<ReadingSource | "all">("all");
  const pollingInterval = usePollingInterval();
  useEffect(() => {
    let active = true;
    const refresh = () => {
      api.analytics(source === "all" ? undefined : source).then((result) => { if (active) { setData(result); setError(""); } })
        .catch((reason: Error) => { if (active) setError(reason.message); })
        .finally(() => { if (active) setLoading(false); });
    };
    refresh();
    const timer = window.setInterval(refresh, pollingInterval * 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [source, pollingInterval]);
  return <>
    <div className="page-heading"><div><div className="eyebrow">CONSUMPTION REVIEW <span>·</span> SQLITE AGGREGATES</div><h1>Energy <em>analytics</em></h1><p>Historical usage and load summaries from stored sensor readings.</p></div><label className="source-picker"><span>DATA SOURCE</span><select value={source} onChange={(event) => { setLoading(true); setSource(event.target.value as ReadingSource | "all"); }} aria-label="Analytics data source"><option value="all">All sources</option><option value="wokwi_simulation">Wokwi simulation</option><option value="live">Other live sensor</option><option value="campus">Authorized campus data</option><option value="public_dataset">Public dataset</option><option value="demo">Generated demo data</option></select></label></div>
    {error && <div className="inline-alert error-alert">{error}</div>}
    {!loading && data && data.reading_count === 0 && <div className="empty-banner">No readings stored yet. Analytics will appear when sensor data arrives.</div>}
    <section className="metric-grid analytics-metrics">
      <Metric label="TOTAL ENERGY" value={data?.total_energy.toFixed(4) ?? "--"} unit="kWh" />
      <Metric label="AVERAGE POWER" value={data?.average_power.toFixed(1) ?? "--"} unit="W" />
      <Metric label="MINIMUM POWER" value={data?.minimum_power.toFixed(1) ?? "--"} unit="W" />
      <Metric label="PEAK POWER" value={data?.peak_power.toFixed(1) ?? "--"} unit="W" />
      <Metric label="AVERAGE CURRENT" value={data?.average_current.toFixed(2) ?? "--"} unit="A" />
      <Metric label="ANOMALY EVENTS" value={String(data?.anomaly_count ?? "--")} unit="events" />
      <Metric label="ANOMALY SHARE" value={data ? data.anomaly_percentage.toFixed(2) : "--"} unit="%" />
    </section>
    <section className="analysis-grid">
      <article className="panel chart-panel"><div className="panel-heading"><div><span className="panel-kicker">DAILY TOTAL</span><h2>Daily energy use</h2></div><span className="chart-unit">KWH / DAY</span></div>{data?.daily.length ? <DailyEnergyChart analytics={data} /> : <div className="chart-empty">{loading ? "Loading analytics…" : "No daily totals available"}</div>}</article>
      <article className="panel chart-panel"><div className="panel-heading"><div><span className="panel-kicker">WEEKLY TOTAL</span><h2>Weekly energy use</h2></div><span className="chart-unit">KWH / WEEK</span></div>{data?.weekly.length ? <DailyEnergyChart analytics={data} dataKey="weekly" /> : <div className="chart-empty">{loading ? "Loading analytics…" : "No weekly totals available"}</div>}</article>
      <article className="panel chart-panel"><div className="panel-heading"><div><span className="panel-kicker">MONTHLY TOTAL</span><h2>Monthly energy use</h2></div><span className="chart-unit">KWH / MONTH</span></div>{data?.monthly.length ? <DailyEnergyChart analytics={data} dataKey="monthly" /> : <div className="chart-empty">{loading ? "Loading analytics…" : "No monthly totals available"}</div>}</article>
      <article className="panel analysis-note"><span className="panel-kicker">MEASUREMENT NOTE</span><h2>Energy is interval-based</h2><p>Each sensor record stores energy used during its sampling interval. The totals on this page sum those intervals; they do not represent a utility meter’s lifetime cumulative register.</p><div className="note-rule" /><span className="muted-label">READINGS PROCESSED</span><strong>{data?.reading_count ?? (loading ? "Loading" : "0")}</strong></article>
    </section>
    <section className="panel latest-panel"><div className="panel-heading"><div><span className="panel-kicker">PROVENANCE</span><h2>Readings by source</h2></div><span className="chart-unit">SOURCE CATEGORIES REMAIN SEPARATE</span></div>
      {data?.sources.length ? <div className="table-scroll"><table><thead><tr><th>SOURCE</th><th>READINGS</th><th>ENERGY TOTAL</th><th>ANOMALIES</th></tr></thead><tbody>{data.sources.map((item) => <tr key={item.source}><td>{readingSourceLabel(item.source)}</td><td>{item.reading_count}</td><td>{item.total_energy.toFixed(5)} kWh</td><td>{item.anomaly_count}</td></tr>)}</tbody></table></div> : <div className="table-empty">{loading ? "Loading sources…" : "No source totals available"}</div>}
    </section>
  </>;
}