"""Convert a selected BDG2 hourly electricity meter series to project CSV format."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def prepare_bdg2(
    source: Path,
    output: Path,
    *,
    meter_column: str | None = None,
    building_id: str | None = None,
    meter_type: str = "electricity",
    nominal_voltage: float = 230.0,
    interval_hours: float = 1.0,
) -> dict:
    if nominal_voltage <= 0 or interval_hours <= 0:
        raise ValueError("Nominal voltage and interval hours must be positive")
    frame = pd.read_csv(source)
    aliases = {str(column).strip().lower(): column for column in frame.columns}
    timestamp_column = next((aliases[name] for name in ("timestamp", "datetime", "date", "time") if name in aliases), None)
    if timestamp_column is None:
        raise ValueError("BDG2 CSV needs a timestamp, datetime, date, or time column")

    reading_column = next((aliases[name] for name in ("meter_reading", "reading", "energy", "kwh") if name in aliases), None)
    if reading_column:
        selected = frame.copy()
        building_column = next((aliases[name] for name in ("building_id", "building", "site_id") if name in aliases), None)
        if building_id is not None:
            if building_column is None:
                raise ValueError("A building ID was requested but this file has no building identifier column")
            selected = selected[selected[building_column].astype(str) == str(building_id)]
        type_column = next((aliases[name] for name in ("meter_type", "meter", "meter_name") if name in aliases), None)
        if type_column:
            selected = selected[selected[type_column].astype(str).str.lower() == meter_type.lower()]
        energy = pd.to_numeric(selected[reading_column], errors="coerce")
    else:
        selected_column = meter_column or (str(building_id) if building_id is not None else None)
        if selected_column is None:
            candidates = [column for column in frame.columns if column != timestamp_column]
            numeric_candidates = [column for column in candidates if pd.to_numeric(frame[column], errors="coerce").notna().any()]
            if len(numeric_candidates) != 1:
                raise ValueError("Wide BDG2 files need --meter-column to select exactly one building meter")
            selected_column = numeric_candidates[0]
        if selected_column not in frame.columns:
            raise ValueError(f"Meter column {selected_column!r} was not found in the CSV")
        selected = frame[[timestamp_column, selected_column]].copy()
        energy = pd.to_numeric(selected[selected_column], errors="coerce")

    timestamp = pd.to_datetime(selected[timestamp_column], errors="coerce", utc=True)
    valid = timestamp.notna() & energy.notna() & np.isfinite(energy) & (energy >= 0)
    if not valid.any():
        raise ValueError("No valid, non-negative energy meter records remain after selection")
    energy = energy[valid].astype(float)
    average_power_w = energy * 1000.0 / interval_hours
    result = pd.DataFrame({
        "timestamp": timestamp[valid].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "voltage": nominal_voltage,
        "current": average_power_w / nominal_voltage,
        "power": average_power_w,
        "energy": energy,
    }).sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    result.to_csv(output, index=False)
    metadata = {
        "source": "Building Data Genome Project 2",
        "source_url": "https://github.com/buds-lab/building-data-genome-project-2",
        "source_file": str(source),
        "selected_meter_column": meter_column,
        "building_id": building_id,
        "meter_type": meter_type,
        "interval_hours": interval_hours,
        "nominal_voltage_assumption": nominal_voltage,
        "voltage_and_current": "derived from energy and nominal voltage; not measured by BDG2",
        "rows": len(result),
    }
    output.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Downloaded BDG2 meter CSV")
    parser.add_argument("output", type=Path, help="Normalized project-format CSV")
    parser.add_argument("--meter-column", help="Exact wide-format meter column to select")
    parser.add_argument("--building-id", help="Building ID for long-format data, or a wide-format column name")
    parser.add_argument("--meter-type", default="electricity")
    parser.add_argument("--nominal-voltage", type=float, default=230.0)
    parser.add_argument("--interval-hours", type=float, default=1.0)
    args = parser.parse_args()
    print(json.dumps(prepare_bdg2(
        args.source, args.output,
        meter_column=args.meter_column,
        building_id=args.building_id,
        meter_type=args.meter_type,
        nominal_voltage=args.nominal_voltage,
        interval_hours=args.interval_hours,
    ), indent=2))


if __name__ == "__main__":
    main()