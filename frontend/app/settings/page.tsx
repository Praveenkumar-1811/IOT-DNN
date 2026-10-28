"use client";

import { useEffect, useState } from "react";
import { Check, FileUp, RefreshCw } from "lucide-react";
import Link from "next/link";
import { API_URL, api, type AppSettings, type DatasetReplayStatus, type ModelStatus } from "@/lib/api";
import { savePollingInterval, usePollingInterval } from "@/lib/settings";

export default function SettingsPage() {
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [replay, setReplay] = useState<DatasetReplayStatus | null>(null);
  const [replayBusy, setReplayBusy] = useState(false);
  const interval = usePollingInterval();
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    Promise.all([api.model(), api.settings()])
      .then(([nextModel, nextSettings]) => { setModel(nextModel); setSettings(nextSettings); })
      .catch((reason: Error) => setError(reason.message));
  }, []);
  useEffect(() => {
    let active = true;
    const refreshReplayStatus = () => {
      api.datasetReplay().then((status) => { if (active) setReplay(status); })
        .catch((reason: Error) => { if (active) setError(reason.message); });
    };
    refreshReplayStatus();
    const timer = window.setInterval(refreshReplayStatus, interval * 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [interval]);
  const toggleReplay = async () => {
    setReplayBusy(true);
    setError("");
    try { setReplay(replay?.running ? await api.stopDatasetReplay() : await api.startDatasetReplay()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Dataset replay could not be changed."); }
    finally { setReplayBusy(false); }
  };
  const changeInterval = (value: number) => {
    savePollingInterval(value);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  };
  const changeReplayInterval = async (value: number) => {
    setError("");
    try { setSettings(await api.updateSettings(value)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save the replay interval."); }
  };
  return <>
    <div className="page-heading"><div><div className="eyebrow">SYSTEM CONFIGURATION <span>·</span> LOCAL WORKSPACE</div><h1>System <em>settings</em></h1><p>Connection details, refresh behavior, and data import.</p></div></div>
    {error && <div className="inline-alert error-alert">{error}</div>}
    <section className="settings-layout">
      <article className="panel settings-section"><div className="panel-heading"><div><span className="panel-kicker">CONNECTION</span><h2>FastAPI service</h2></div><span className="settings-live"><i />CONFIGURED</span></div><div className="setting-row"><div><strong>API base URL</strong><small>Set through NEXT_PUBLIC_API_URL at build time</small></div><code>{API_URL}</code></div><div className="setting-row"><div><strong>Dashboard polling</strong><small>Fastest recommended refresh when Wokwi sends once per second</small></div><div className="setting-edit"><select value={interval} onChange={(event) => changeInterval(Number(event.target.value))} aria-label="Polling interval"><option value={1}>Every second</option><option value={2}>Every 2 seconds</option><option value={5}>Every 5 seconds</option><option value={10}>Every 10 seconds</option></select><span className="saved-indicator">{saved && <Check size={14} />}</span></div></div><p className="settings-footnote">Dashboard polling fetches existing backend records; it never creates readings. Set Wokwi to send a new sample every second for second-by-second live updates.</p></article>
      <article className="panel settings-section"><div className="panel-heading"><div><span className="panel-kicker">REPLAY CONTROL</span><h2>Demo replay interval</h2></div></div><div className="setting-row"><div><strong>Backend replay cadence</strong><small>Persisted by the API; does not affect Wokwi transmission</small></div><div className="setting-edit"><select value={settings?.dataset_replay_interval_seconds ?? 60} onChange={(event) => void changeReplayInterval(Number(event.target.value))} aria-label="Demo replay interval"><option value={5}>5 seconds</option><option value={15}>15 seconds</option><option value={30}>30 seconds</option><option value={60}>60 seconds</option><option value={300}>5 minutes</option></select></div></div></article>
      <article className="panel settings-section"><div className="panel-heading"><div><span className="panel-kicker">MODEL CONTROL</span><h2>Learned threshold</h2></div></div><div className="setting-row"><div><strong>Autoencoder threshold</strong><small>Learned from normal validation errors · {model?.threshold_percentile ?? 95}th percentile</small></div><code>{model?.threshold?.toFixed(7) ?? "Not available"}</code></div><div className="readonly-note"><span className="readonly-lock">LOCKED</span><span>This setting is read-only. Re-train the model to produce a new threshold; manual edits are not supported.</span></div></article>
      <article className="panel settings-section"><div className="panel-heading"><div><span className="panel-kicker">DATA INGESTION</span><h2>Import building readings</h2></div></div><p className="settings-description">Preview CSV columns, choose provenance, and review accepted, rejected, and duplicate rows in the dataset manager.</p><Link className="small-action settings-link" href="/datasets"><FileUp size={15} /> Open dataset manager</Link><div className="csv-format">Required: timestamp, voltage, current · power and interval energy can be derived when missing.</div></article>
      <article className="settings-aside"><span className="panel-kicker">DATASET REPLAY</span><h2>{replay?.running ? "Replay is live" : "Replay is paused"}</h2><p>{replay?.dataset ?? "demo_energy_data.csv"} · one scored reading every {replay?.interval_seconds ?? 60} seconds. Records remain tagged as demo data, separate from ESP32 readings.</p><div className="mode-line"><span className="mode-dot" />{replay?.running ? `${replay.rows_processed} READINGS PROCESSED` : "REPLAY INACTIVE"}</div><div className="mode-line mode-secondary"><RefreshCw size={14} />{replay?.dataset_rows ?? "Dataset"} SOURCE ROWS</div>{replay?.last_error && <div className="inline-alert error-alert">{replay.last_error}</div>}<button className="small-action" onClick={() => void toggleReplay()} disabled={replayBusy}>{replayBusy ? "Please wait…" : replay?.running ? "Stop replay" : "Start replay"}</button></article>
    </section>
  </>;
}