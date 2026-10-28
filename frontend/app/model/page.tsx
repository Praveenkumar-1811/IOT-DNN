"use client";

import { useEffect, useState } from "react";
import { Check, CircleAlert, Cpu } from "lucide-react";
import { api, type ModelStatus } from "@/lib/api";

export default function ModelPage() {
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.model().then(setModel).catch((reason: Error) => setError(reason.message)); }, []);
  return <>
    <div className="page-heading"><div><div className="eyebrow">MACHINE LEARNING <span>·</span> UNSUPERVISED DETECTION</div><h1>Model <em>information</em></h1><p>Model readiness, input features, and the learned decision boundary.</p></div></div>
    {error && <div className="inline-alert error-alert">{error}</div>}
    <section className="model-overview panel"><div className="model-emblem"><Cpu size={25} /></div><div className="model-copy"><span className="panel-kicker">ACTIVE DETECTOR</span><h2>{model?.name ?? "Autoencoder status"}</h2><p>A dense neural network trained to reconstruct normal energy observations. Large reconstruction error flags an abnormal pattern.</p></div><div className={`model-ready ${model?.available ? "ready" : "not-ready"}`}>{model?.available ? <Check size={14} /> : <CircleAlert size={14} />}{model ? model.available ? "MODEL READY" : "MODEL UNAVAILABLE" : "CHECKING MODEL"}</div></section>
    {model && !model.available && <div className="inline-alert warning-alert">{model.message}</div>}
    {!model && !error && <div className="inline-alert warning-alert">Checking model readiness…</div>}
    <section className="model-detail-grid">
      <article className="panel model-detail"><span className="panel-kicker">INPUT SPACE</span><h2>Four measured features</h2><div className="feature-list">{(model?.features ?? ["voltage", "current", "power", "energy"]).map((feature, index) => <div key={feature}><span className="feature-index">0{index + 1}</span><strong>{feature.charAt(0).toUpperCase() + feature.slice(1)}</strong><small>{["V", "A", "W", "kWh per interval"][index]}</small></div>)}</div></article>
      <article className="panel model-detail"><span className="panel-kicker">NETWORK & LOSS</span><h2>Reconstruction architecture</h2><div className="architecture-line"><span>INPUT</span><i /> <b>16</b><i /> <b>8</b><i /> <b className="latent">4</b><i /> <b>8</b><i /> <b>16</b><i /> <span>OUTPUT</span></div><div className="model-property"><span>Architecture</span><strong>{model?.architecture ?? "Checking API…"}</strong></div><div className="model-property"><span>Optimizer</span><strong>Adam</strong></div><div className="model-property"><span>Loss function</span><strong>{model?.loss ?? "Checking API…"}</strong></div><div className="model-property"><span>Input normalization</span><strong>StandardScaler</strong></div></article>
      <article className="panel model-detail threshold-panel"><span className="panel-kicker">LEARNED DECISION BOUNDARY</span><h2>Validation percentile</h2><div className="threshold-number">{model?.threshold !== null && model?.threshold !== undefined ? model.threshold.toFixed(7) : "--"}</div><p>The threshold is the {model?.threshold_percentile ?? 95}th percentile of reconstruction error on held-out normal validation readings.</p><div className="model-property"><span>Training examples</span><strong>{model?.training_samples || "--"}</strong></div><div className="model-property"><span>Training sample interval</span><strong>{model?.sampling_interval_seconds ?? 5}s</strong></div><div className="model-property"><span>Last trained</span><strong>{model?.last_trained_at ? new Date(model.last_trained_at).toLocaleString() : "Not available"}</strong></div></article>
      <article className="panel limitation-panel"><span className="panel-kicker">INTERPRETATION</span><h2>Pattern, not diagnosis</h2><p>An anomaly indicates that a reading differs from learned normal data. These measurements do not establish a specific equipment fault or explain its cause.</p><div className="limitation-tag">UNSUPERVISED · NO FAULT LABELS</div></article>
    </section>
  </>;
}