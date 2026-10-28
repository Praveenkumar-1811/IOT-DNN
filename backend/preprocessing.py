from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = ["voltage", "current", "power", "energy"]
LABEL_COLUMNS = ("anomaly", "label", "is_anomaly", "ground_truth", "is_anomalous")
COLUMN_ALIASES = {
    "date": "timestamp",
    "datetime": "timestamp",
    "time": "timestamp",
    "amps": "current",
    "amp": "current",
    "volts": "voltage",
    "watt": "power",
    "watts": "power",
    "kwh": "energy",
    "energy_kwh": "energy",
}


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.copy()
    renamed.columns = [COLUMN_ALIASES.get(str(name).strip().lower(), str(name).strip().lower()) for name in renamed.columns]
    return renamed


def clean_dataset(frame: pd.DataFrame) -> pd.DataFrame:
    data = normalize_columns(frame)
    if "timestamp" not in data:
        raise ValueError("CSV must include a timestamp column")
    if not {"voltage", "current"}.issubset(data.columns):
        raise ValueError("CSV must include voltage and current columns")

    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce", utc=True)
    for name in ("voltage", "current", "power", "energy"):
        if name not in data:
            data[name] = np.nan
        data[name] = pd.to_numeric(data[name], errors="coerce")

    data = data.replace([np.inf, -np.inf], np.nan).dropna(subset=["timestamp", "voltage", "current"])
    if (data["voltage"] <= 0).any() or (data["current"] < 0).any() or (data["voltage"] > 1000).any() or (data["current"] > 10_000).any():
        raise ValueError("CSV contains physically invalid voltage or current values")
    calculated_power = data["voltage"] * data["current"]
    reported_power = data["power"]
    inconsistent = reported_power.notna() & ((reported_power - calculated_power).abs() > np.maximum(50, calculated_power * 0.25))
    if inconsistent.any():
        raise ValueError("CSV contains power values inconsistent with voltage × current")
    data["power"] = calculated_power
    data["energy"] = data["energy"].fillna(data["power"] * 5 / 3_600_000)
    if (data[["power", "energy"]] < 0).any().any():
        raise ValueError("CSV contains negative power or energy values")
    data = data.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")
    data[FEATURES] = data[FEATURES].fillna(data[FEATURES].median(numeric_only=True))
    return data.reset_index(drop=True)


def clean_dataset_with_report(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict], int]:
    """Clean an import row by row so rejected and duplicate rows remain auditable."""
    normalized = normalize_columns(frame)
    if "timestamp" not in normalized:
        raise ValueError("CSV must include a timestamp column")
    if not {"voltage", "current"}.issubset(normalized.columns):
        raise ValueError("CSV must include voltage and current columns")

    accepted: list[pd.DataFrame] = []
    errors: list[dict] = []
    seen_timestamps: set[str] = set()
    duplicates = 0
    for row_number, (_, row) in enumerate(normalized.iterrows(), start=2):
        timestamp = pd.to_datetime(row.get("timestamp"), errors="coerce", utc=True)
        if pd.isna(timestamp):
            errors.append({"row": row_number, "error": "Invalid or missing timestamp"})
            continue
        key = timestamp.isoformat()
        if key in seen_timestamps:
            duplicates += 1
            errors.append({"row": row_number, "error": "Duplicate timestamp"})
            continue
        try:
            cleaned = clean_dataset(pd.DataFrame([row]))
        except ValueError as exc:
            errors.append({"row": row_number, "error": str(exc)})
            continue
        if cleaned.empty:
            errors.append({"row": row_number, "error": "Missing or invalid voltage/current"})
            continue
        seen_timestamps.add(key)
        cleaned["_csv_row"] = row_number
        accepted.append(cleaned)

    result = pd.concat(accepted, ignore_index=True) if accepted else pd.DataFrame(columns=["timestamp", *FEATURES])
    return result, errors, duplicates


def find_label_column(frame: pd.DataFrame) -> str | None:
    return next((name for name in LABEL_COLUMNS if name in frame.columns), None)


def labels_are_anomalies(labels: pd.Series) -> np.ndarray:
    if pd.api.types.is_bool_dtype(labels):
        return labels.fillna(False).to_numpy(dtype=bool)
    numeric = pd.to_numeric(labels, errors="coerce")
    if numeric.notna().any():
        return numeric.fillna(0).to_numpy() > 0
    return labels.astype(str).str.strip().str.lower().isin({"true", "yes", "anomaly", "abnormal", "fault"}).to_numpy()


def feature_vector(voltage: float, current: float, power: float, energy: float) -> np.ndarray:
    values = np.asarray([[voltage, current, power, energy]], dtype=np.float32)
    if not np.isfinite(values).all() or (values < 0).any() or voltage <= 0:
        raise ValueError("Reading contains invalid physical values")
    return values