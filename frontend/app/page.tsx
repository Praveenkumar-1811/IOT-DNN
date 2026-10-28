"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, RefreshCw, Zap } from "lucide-react";
import { api, readingSourceLabel, type Analytics, type Reading, type ReadingSource } from "@/lib/api";
import { DailyEnergyChart, ScoreThresholdChart, StatusDonut, TrendChart } from "@/components/charts";
import { usePollingInterval } from "@/lib/settings";

function Metric({ label, value, unit, detail, tone }: { label: string; value: string; unit: string; detail: string; tone?: string }) {
  return <article className="metric-card"><div className="metric-heading"><span>{label}</span><span className={`metric-mark ${tone ?? ""}`} /></div><div className="metric-value">{value}<small>{unit}</small></div><div className="metric-detail">{detail}</div></article>;
}

export default function DashboardPage() {
  const [latest, setLatest] = useState<Reading | null>(null);
  const [readings, setReadings] = useState<Reading[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [now, setNow] = useState<number | null>(null);
  const pollingInterval = usePollingInterval();
  const [source, setSource] = useState<ReadingSource>("wokwi_simulation");
  const refreshPending = useRef(false);

  const refresh = useCallback(async () => {
    if (refreshPending.current) return;
    refreshPending.current = true;
    try {
      const nextReadings = await api.readings(72, source);
      setLatest(nextReadings[0] ?? null);
      setReadings(nextReadings);
      setUpdatedAt(new Date());
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load building readings.");
    } finally {
      refreshPending.current = false;
      setLoading(false);
    }
  }, [source]);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    const pollAnalytics = async () => {
      try {
        const nextAnalytics = await api.analytics(source);
        if (active) setAnalytics(nextAnalytics);
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Unable to load energy analytics.");
      }
      if (active) timer = window.setTimeout(() => void pollAnalytics(), 10_000);
    };
    void pollAnalytics();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [source]);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    const poll = async () => {
      await refresh();
      if (active) setNow(Date.now());
      if (active) timer = window.setTimeout(() => void poll(), pollingInterval * 1000);
    };
    void poll();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [pollingInterval, refresh]);

  const readingAgeSeconds = latest && now !== null ? Math.max(0, Math.floor((now - new Date(latest.timestamp).getTime()) / 1000)) : null;
  const sensorSource = source === "wokwi_simulation" || source === "live";
  const deviceOnline = sensorSource && !error && readingAgeSeconds !== null && readingAgeSeconds <= 3;
  return <>
    <div className="page-heading dashboard-heading">
      <div><div className="eyebrow">BUILDING 01 <span>·</span> ENERGY SYSTEMS</div><h1>Building Energy <em>Intelligence</em></h1><p>Electrical load monitoring and learned-pattern anomaly detection.</p></div>
      <div className="heading-actions"><label className="source-picker"><span>DATA SOURCE</span><select value={source} onChange={(event) => setSource(event.target.value as ReadingSource)} aria-label="Dashboard data source"><option value="wokwi_simulation">Wokwi simulation</option><option value="live">Other live sensor</option><option value="campus">Authorized campus data</option><option value="public_dataset">Public dataset</option><option value="demo">Generated demo data</option></select></label><button className="icon-button" onClick={() => void refresh()} title="Refresh readings" aria-label="Refresh readings"><RefreshCw size={16} /></button></div>
    </div>
    <div className={`feed-status ${sensorSource ? deviceOnline ? "feed-online" : "feed-waiting" : "feed-source"}`} role="status">
      <span className="feed-status-dot" />
      <strong>{source === "wokwi_simulation" ? deviceOnline ? "WOKWI SIMULATION CONNECTED" : "WAITING FOR WOKWI DEVICE" : source === "live" ? deviceOnline ? "LIVE SENSOR CONNECTED" : "WAITING FOR LIVE SENSOR" : `${readingSourceLabel(source).toUpperCase()} SOURCE`}</strong>
      <span>{latest ? `Last sample ${readingAgeSeconds ?? "--"}s ago · ${latest.interval_seconds.toFixed(1)}s interval${latest.device_id ? ` · Device ${latest.device_id}` : ""}` : source === "wokwi_simulation" ? "Start Wokwi and enable its Private IoT Gateway to stream simulated readings" : "No readings stored for this source yet"}</span>
      <span className="feed-cadence">UI REFRESH · {pollingInterval}s</span>
    </div>
    {error && <div className="inline-alert error-alert"><span>{error}</span><button className="text-button" onClick={() => void refresh()}>Retry</button></div>}
    {latest?.status === "ANOMALY" && <div className="anomaly-banner"><span className="alert-icon"><Zap size={17} /></span><div><strong>Abnormal energy pattern detected</strong><small>{new Date(latest.timestamp).toLocaleString()} · {latest.power.toFixed(0)} W · {latest.severity} severity</small></div><Link href="/anomalies">Review event <ArrowUpRight size={14} /></Link></div>}
    <section className="metric-grid" aria-label="Latest energy reading">
      <Metric label="CURRENT POWER" value={latest ? latest.power.toFixed(0) : "--"} unit="W" detail={latest ? `Peak recorded ${analytics?.peak_power.toFixed(0) ?? "--"} W` : "Awaiting first sensor reading"} tone="amber" />
      <Metric label="CURRENT" value={latest ? latest.current.toFixed(2) : "--"} unit="A" detail={source === "wokwi_simulation" ? "Potentiometer-simulated current" : "Stored reading"} />
      <Metric label="VOLTAGE" value={latest ? latest.voltage.toFixed(1) : "--"} unit="V" detail={source === "wokwi_simulation" ? "Simulated value · not a physical measurement" : source === "live" ? "Device-reported value" : "Imported or derived value"} tone="blue" />
      <Metric label="INTERVAL ENERGY" value={latest ? latest.energy.toFixed(5) : "--"} unit="kWh" detail="Latest sampling interval" tone="mint" />
    </section>
    <section className="status-strip">
      <div className={`reading-state ${!latest ? "state-empty" : latest.status === "ANOMALY" ? "state-anomaly" : "state-normal"}`}><span className="state-symbol">{!latest ? "—" : latest.status === "ANOMALY" ? "!" : "✓"}</span><div><small>CURRENT STATUS</small><strong>{latest ? latest.status : loading ? "CONNECTING" : "NO DATA"}</strong></div></div>
      <div className="status-stat"><small>ANOMALY SCORE</small><strong>{latest ? latest.anomaly_score.toFixed(6) : "--"}</strong></div>
      <div className="status-stat"><small>LEARNED THRESHOLD</small><strong>{latest ? latest.threshold.toFixed(6) : "--"}</strong></div>
      <div className="status-stat"><small>TOTAL ANOMALIES</small><strong>{analytics?.anomaly_count ?? "--"}</strong></div>
      <div className="status-update"><span className="pulse-dot" />{updatedAt ? `Updated ${updatedAt.toLocaleTimeString()}` : "Waiting for API"}</div>
    </section>
    {!loading && !error && !latest && <div className="empty-banner">{source === "wokwi_simulation" ? "No Wokwi samples yet. Start the simulation and enable the Private IoT Gateway. Demo, public and campus sources remain separate." : `No readings stored for ${readingSourceLabel(source)} yet.`}</div>}
    <section className="chart-grid">
      <article className="panel chart-panel chart-wide"><div className="panel-heading"><div><span className="panel-kicker">ELECTRICAL LOAD</span><h2>Power consumption</h2></div><span className="chart-unit">WATTS · RECENT READINGS</span></div>
        {readings.length ? <TrendChart readings={readings} dataKey="power" color="#167a67" unit="W" /> : <div className="chart-empty">{loading ? "Loading readings…" : "No readings available"}</div>}
      </article>
      <article className="panel chart-panel"><div className="panel-heading"><div><span className="panel-kicker">VOLTAGE</span><h2>Voltage over time</h2></div><span className="chart-unit">VOLTS</span></div>
        {readings.length ? <TrendChart readings={readings} dataKey="voltage" color="#537fa0" unit="V" /> : <div className="chart-empty">{loading ? "Loading readings…" : "No readings available"}</div>}
      </article>
      <article className="panel chart-panel"><div className="panel-heading"><div><span className="panel-kicker">CURRENT</span><h2>Current over time</h2></div><span className="chart-unit">AMPERES</span></div>
        {readings.length ? <TrendChart readings={readings} dataKey="current" color="#d08a31" unit="A" /> : <div className="chart-empty">{loading ? "Loading readings…" : "No readings available"}</div>}
      </article>
      <article className="panel chart-panel chart-wide"><div className="panel-heading"><div><span className="panel-kicker">MODEL DEVIATION</span><h2>Anomaly score vs threshold</h2></div><span className="chart-unit">RECONSTRUCTION ERROR</span></div>
        {readings.length ? <ScoreThresholdChart readings={readings} /> : <div className="chart-empty">{loading ? "Loading readings…" : "No readings available"}</div>}
      </article>
      <article className="panel chart-panel"><div className="panel-heading"><div><span className="panel-kicker">METERED USAGE</span><h2>Energy interval</h2></div><span className="chart-unit">KWH</span></div>
        {readings.length ? <TrendChart readings={readings} dataKey="energy" color="#d08a31" unit="kWh" /> : <div className="chart-empty">{loading ? "Loading readings…" : "No readings available"}</div>}
      </article>
      <article className="panel chart-panel"><div className="panel-heading"><div><span className="panel-kicker">DAILY AGGREGATE</span><h2>Energy by day</h2></div><Link className="text-link" href="/analytics">All analytics <ArrowUpRight size={13} /></Link></div>
        {analytics?.daily.length ? <DailyEnergyChart analytics={analytics} /> : <div className="chart-empty">{loading ? "Loading analytics…" : "No daily totals yet"}</div>}
      </article>
      <article className="panel chart-panel composition-panel"><div className="panel-heading"><div><span className="panel-kicker">READING CLASSIFICATION</span><h2>Normal vs anomaly</h2></div></div>
        {analytics?.reading_count ? <><div className="classification"><StatusDonut normal={analytics.reading_count - analytics.anomaly_count} anomaly={analytics.anomaly_count} /><div className="legend"><span><i className="legend-normal" />Normal <b>{analytics.reading_count - analytics.anomaly_count}</b></span><span><i className="legend-alert" />Anomaly <b>{analytics.anomaly_count}</b></span></div></div><p className="fine-print">Classification follows reconstruction error against the learned validation threshold.</p></> : <div className="chart-empty">{loading ? "Loading analytics…" : "No readings available"}</div>}
      </article>
    </section>
    <section className="panel latest-panel"><div className="panel-heading"><div><span className="panel-kicker">LATEST SENSOR EVENTS</span><h2>Recent readings</h2></div><Link className="text-link" href="/anomalies">Anomaly history <ArrowUpRight size={13} /></Link></div>
      {readings.length ? <div className="table-scroll"><table><thead><tr><th>TIME</th><th>POWER</th><th>CURRENT</th><th>ENERGY</th><th>ERROR SCORE</th><th>STATUS</th></tr></thead><tbody>{readings.slice(0, 5).map((reading) => <tr key={reading.id}><td>{new Date(reading.timestamp).toLocaleString()}</td><td>{reading.power.toFixed(1)} W</td><td>{reading.current.toFixed(2)} A</td><td>{reading.energy.toFixed(5)} kWh</td><td>{reading.anomaly_score.toFixed(6)}</td><td><span className={`table-status ${reading.status === "ANOMALY" ? "status-bad" : "status-good"}`}>{reading.status}</span></td></tr>)}</tbody></table></div> : <div className="table-empty">{loading ? "Loading recent readings…" : "No readings stored"}</div>}
    </section>
    <footer className="page-footer"><span>{readingSourceLabel(source).toUpperCase()} · PROVENANCE RECORDED{source === "wokwi_simulation" ? " · SIMULATED VALUES" : ""}</span><span>{updatedAt ? <><ArrowDownRight size={12} /> POLLING EVERY {pollingInterval} SECONDS</> : "API CONNECTION PENDING"}</span></footer>
  </>;
}
