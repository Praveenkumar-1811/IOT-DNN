export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
export type ReadingSource = "live" | "wokwi_simulation" | "campus" | "public_dataset" | "demo";
export type ReadingStatus = "NORMAL" | "ANOMALY";
export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export function readingSourceLabel(source: ReadingSource): string {
  switch (source) {
    case "wokwi_simulation": return "Wokwi simulation";
    case "campus": return "Authorized campus measurement";
    case "public_dataset": return "Public dataset";
    case "demo": return "Generated demo data";
    default: return "Live sensor";
  }
}

export type Reading = {
  id: number;
  timestamp: string;
  voltage: number;
  current: number;
  power: number;
  energy: number;
  interval_energy_kwh: number;
  interval_seconds: number;
  cumulative_energy_kwh: number | null;
  anomaly_score: number;
  threshold: number;
  status: ReadingStatus;
  severity: Severity;
  source: ReadingSource;
  import_id: number | null;
  model_version: string;
  device_id: string | null;
  request_id: string | null;
  data_source: "wokwi_simulation" | null;
};

export type Analytics = {
  reading_count: number;
  total_energy: number;
  average_energy: number;
  average_power: number;
  minimum_power: number;
  peak_power: number;
  average_current: number;
  anomaly_count: number;
  anomaly_percentage: number;
  daily: { day: string; energy: number; average_power: number; peak_power: number; reading_count: number; anomaly_count: number }[];
  weekly: { period: string; energy: number; reading_count: number }[];
  monthly: { period: string; energy: number; reading_count: number }[];
  sources: { source: ReadingSource; reading_count: number; total_energy: number; anomaly_count: number }[];
};

export type ModelStatus = {
  available: boolean;
  name: string;
  features: string[];
  architecture: string;
  loss: string;
  threshold: number | null;
  sampling_interval_seconds: number;
  threshold_percentile: number;
  training_samples: number;
  last_trained_at: string | null;
  message: string;
};

export type DatasetReplayStatus = {
  running: boolean;
  source: "demo";
  dataset: string;
  interval_seconds: number;
  rows_processed: number;
  dataset_rows: number;
  last_error: string | null;
};

export type DatasetImport = {
  id: number;
  filename: string;
  source: ReadingSource;
  imported_at: string;
  total_rows: number;
  accepted_rows: number;
  imported: number;
  rejected_rows: number;
  duplicate_rows: number;
  errors: { row: number; error: string }[];
};

export type AppSettings = {
  dataset_replay_interval_seconds: number;
  threshold_percentile: number;
  max_csv_upload_mb: number;
};

export type ImportReport = DatasetImport;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, cache: "no-store" });
  } catch {
    throw new Error("Backend unavailable. Check the API server and try again.");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail || `API request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  latest: (source?: ReadingSource) => request<Reading | null>(`/readings/latest${source ? `?source=${source}` : ""}`),
  readings: (limit = 120, source?: ReadingSource, status?: ReadingStatus, days?: number, offset = 0, since?: string, until?: string) => {
    const sinceValue = since ?? (days ? new Date(Date.now() - days * 86_400_000).toISOString() : undefined);
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (source) params.set("source", source);
    if (status) params.set("status", status);
    if (sinceValue) params.set("since", sinceValue);
    if (until) params.set("until", until);
    return request<Reading[]>(`/readings?${params}`);
  },
  anomalies: (days?: number, source?: ReadingSource) => request<Reading[]>(`/anomalies?limit=1000${days ? `&days=${days}` : ""}${source ? `&source=${source}` : ""}`),
  analytics: (source?: ReadingSource) => request<Analytics>(`/analytics${source ? `?source=${source}` : ""}`),
  model: () => request<ModelStatus>("/model/status"),
  health: () => request<{ status: string; database: boolean; model: boolean }>("/health"),
  count: (source?: ReadingSource, status?: ReadingStatus, since?: string, until?: string) => {
    const params = new URLSearchParams();
    if (source) params.set("source", source);
    if (status) params.set("status", status);
    if (since) params.set("since", since);
    if (until) params.set("until", until);
    return request<{ count: number }>(`/readings/count${params.size ? `?${params}` : ""}`);
  },
  datasets: (limit = 100, offset = 0) => request<DatasetImport[]>(`/datasets?limit=${limit}&offset=${offset}`),
  settings: () => request<AppSettings>("/settings"),
  updateSettings: (dataset_replay_interval_seconds: number) => request<AppSettings>("/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_replay_interval_seconds }),
  }),
  datasetReplay: () => request<DatasetReplayStatus>("/dataset-replay"),
  startDatasetReplay: () => request<DatasetReplayStatus>("/dataset-replay/start", { method: "POST" }),
  stopDatasetReplay: () => request<DatasetReplayStatus>("/dataset-replay/stop", { method: "POST" }),
  upload: async (file: File, source: Exclude<ReadingSource, "live" | "wokwi_simulation">) => {
    const body = new FormData();
    body.append("file", file);
    return request<ImportReport>(`/readings/import?source=${source}`, { method: "POST", body });
  },
};