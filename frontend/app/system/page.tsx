"use client";

import { useEffect, useState } from "react";
import { API_URL, api, type AppSettings, type ModelStatus } from "@/lib/api";

export default function SystemStatusPage() {
  const [health, setHealth] = useState<{ status: string; database: boolean; model: boolean } | null>(null);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([api.health(), api.model(), api.settings()])
      .then(([nextHealth, nextModel, nextSettings]) => { setHealth(nextHealth); setModel(nextModel); setSettings(nextSettings); })
      .catch((reason: Error) => setError(reason.message));
  }, []);
  return <>
    <div className="page-heading"><div><div className="eyebrow">SERVICE READINESS <span>·</span> LOCAL PROTOTYPE</div><h1>System <em>status</em></h1><p>Health indicators are based on the API response; no authentication is provided by this prototype.</p></div></div>
    {error && <div className="inline-alert error-alert">{error}</div>}
    <section className="metric-grid"><article className="metric-card"><div className="metric-heading">API</div><div className="metric-value">{health?.status.toUpperCase() ?? "UNKNOWN"}</div><div className="metric-detail">{API_URL}</div></article><article className="metric-card"><div className="metric-heading">DATABASE</div><div className="metric-value">{health ? health.database ? "READY" : "DEGRADED" : "UNKNOWN"}</div><div className="metric-detail">SQLite-backed persistence</div></article><article className="metric-card"><div className="metric-heading">MODEL</div><div className="metric-value">{health ? health.model ? "READY" : "NOT TRAINED" : "UNKNOWN"}</div><div className="metric-detail">{model?.message ?? "Checking model readiness"}</div></article><article className="metric-card"><div className="metric-heading">DEMO REPLAY</div><div className="metric-value">{settings ? `${settings.dataset_replay_interval_seconds}s` : "UNKNOWN"}</div><div className="metric-detail">Configured replay cadence</div></article></section>
    {model && <section className="panel latest-panel"><div className="panel-heading"><div><span className="panel-kicker">TRAINING METADATA</span><h2>{model.name}</h2></div><span className="chart-unit">{model.available ? "READY" : "UNAVAILABLE"}</span></div><div className="setting-row"><div><strong>Features</strong><small>Fixed inference order</small></div><code>{model.features.join(" · ")}</code></div><div className="setting-row"><div><strong>Calibration</strong><small>Held-out normal calibration partition</small></div><code>{model.threshold_percentile}th percentile</code></div><div className="setting-row"><div><strong>Training cadence</strong><small>Energy is normalized to this interval for inference</small></div><code>{model.sampling_interval_seconds}s</code></div><div className="setting-row"><div><strong>Training samples</strong></div><code>{model.training_samples}</code></div><div className="setting-row"><div><strong>Last trained</strong></div><code>{model.last_trained_at ?? "Not available"}</code></div></section>}
    <div className="note-line">Health reports component availability only. This local demonstration has no user authentication and should not be exposed to untrusted public traffic.</div>
  </>;
}
