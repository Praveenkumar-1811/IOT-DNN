import os
import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import database
from backend.dataset_replay import DatasetReplay
from backend.detector import AutoencoderDetector
from backend.preprocessing import clean_dataset_with_report
from backend.schemas import ImportSource, ModelStatus, Reading, ReadingInput, SettingsUpdate, Source

logger = logging.getLogger(__name__)
app = FastAPI(title="Building Energy Intelligence API", version="1.0.0")
origins = [origin.strip() for origin in os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
)
detector = AutoencoderDetector()


@app.on_event("startup")
async def startup() -> None:
    database.initialize_database()
    interval = int(database.get_setting("dataset_replay_interval_seconds", str(replay_interval)))
    dataset_replay.interval_seconds = interval
    if detector.metadata:
        database.save_model_metadata(
            version=str(detector.metadata.get("last_trained_at", "current")),
            training_data=str(detector.metadata.get("training_data", "unknown")),
            features=[
                {"name": "voltage", "unit": "V"},
                {"name": "current", "unit": "A"},
                {"name": "power", "unit": "W"},
                {"name": "energy", "unit": "kWh per interval"},
            ],
            trained_at=str(detector.metadata.get("last_trained_at", "unknown")),
            configuration=detector.metadata,
        )
    if detector.available:
        await dataset_replay.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await dataset_replay.stop()


@app.exception_handler(Exception)
async def handle_unexpected_error(_request, _exc: Exception):
    logger.exception("Unhandled API request error")
    return JSONResponse(status_code=500, content={"detail": "The request could not be completed."})


@app.get("/")
def root() -> dict:
    return {"name": "Building Energy Intelligence API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> dict:
    try:
        database_ok = database.check_health()
    except Exception:
        logger.exception("Health check could not connect to the database")
        database_ok = False
    ready = database_ok and detector.available
    return {"status": "ok" if ready else "degraded", "database": database_ok, "model": detector.available}


@app.post("/reading", response_model=Reading, status_code=201)
def create_reading(payload: ReadingInput, source: Source = "live") -> dict:
    if not detector.available:
        raise HTTPException(
            status_code=503,
            detail=f"Trained model unavailable: {detector.status()['message']}",
        )
    calculated_power = payload.voltage * payload.current
    if payload.power is not None and abs(payload.power - calculated_power) > max(50, calculated_power * 0.25):
        raise HTTPException(status_code=422, detail="Reported power is inconsistent with voltage × current.")
    if payload.data_source == "wokwi_simulation" and source not in ("live", "wokwi_simulation"):
        raise HTTPException(status_code=422, detail="Wokwi simulation readings cannot be stored as another source.")
    reading_source = (
        "wokwi_simulation" if payload.data_source == "wokwi_simulation" else source
    )
    interval_energy_kwh = (
        payload.interval_energy_kwh
        if payload.interval_energy_kwh is not None
        else payload.energy
    )
    if interval_energy_kwh is None:
        raise HTTPException(status_code=422, detail="Provide energy or interval_energy_kwh.")
    interval_seconds = payload.interval_seconds or detector.sampling_interval_seconds
    try:
        result = detector.score(
            payload.voltage,
            payload.current,
            calculated_power,
            interval_energy_kwh,
            interval_seconds,
        )
    except Exception as exc:
        logger.exception("Autoencoder inference failed")
        raise HTTPException(status_code=503, detail="Autoencoder inference failed.") from exc
    record = {
        "timestamp": payload.timestamp.astimezone(timezone.utc).isoformat(),
        "voltage": payload.voltage,
        "current": payload.current,
        "power": calculated_power,
        "energy": interval_energy_kwh,
        "interval_seconds": interval_seconds,
        "cumulative_energy_kwh": payload.cumulative_energy_kwh,
        "source": reading_source,
        "data_source": payload.data_source,
        "device_id": payload.device_id,
        "request_id": payload.request_id,
        **result,
    }
    try:
        return database.insert_reading(record)
    except Exception as exc:
        logger.exception("Reading persistence failed")
        raise HTTPException(status_code=503, detail="Reading could not be stored in the database.") from exc


replay_path = Path(os.getenv("DATASET_REPLAY_PATH", Path(__file__).parent / "data" / "demo_energy_data.csv"))
replay_interval = max(1, int(os.getenv("DATASET_REPLAY_INTERVAL_SECONDS", "60")))
dataset_replay = DatasetReplay(replay_path, replay_interval, create_reading)


@app.get("/dataset-replay")
def get_dataset_replay() -> dict:
    return dataset_replay.status()


@app.post("/dataset-replay/start")
async def start_dataset_replay() -> dict:
    if not detector.available:
        raise HTTPException(status_code=503, detail="Trained model unavailable. Run python -m backend.train first.")
    try:
        return await dataset_replay.start()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/dataset-replay/stop")
async def stop_dataset_replay() -> dict:
    return await dataset_replay.stop()


@app.get("/settings")
def get_settings() -> dict:
    return {
        "dataset_replay_interval_seconds": dataset_replay.interval_seconds,
        "threshold_percentile": float(os.getenv("THRESHOLD_PERCENTILE", "95")),
        "max_csv_upload_mb": 10,
    }


@app.patch("/settings")
def update_settings(payload: SettingsUpdate) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Provide at least one supported setting.")
    if payload.dataset_replay_interval_seconds is not None:
        dataset_replay.interval_seconds = payload.dataset_replay_interval_seconds
        database.set_setting("dataset_replay_interval_seconds", str(payload.dataset_replay_interval_seconds))
    return get_settings()


@app.get("/readings", response_model=list[Reading])
def get_readings(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    since: datetime | None = None,
    until: datetime | None = None,
    source: Source | None = None,
    status: str | None = Query(default=None, pattern="^(NORMAL|ANOMALY)$"),
) -> list[dict]:
    since_text = since.astimezone(timezone.utc).isoformat() if since else None
    until_text = until.astimezone(timezone.utc).isoformat() if until else None
    return database.fetch_readings(limit=limit, offset=offset, since=since_text, until=until_text, source=source, status=status)


@app.get("/readings/count")
def get_readings_count(
    since: datetime | None = None,
    until: datetime | None = None,
    source: Source | None = None,
    status: str | None = Query(default=None, pattern="^(NORMAL|ANOMALY)$"),
) -> dict:
    since_text = since.astimezone(timezone.utc).isoformat() if since else None
    until_text = until.astimezone(timezone.utc).isoformat() if until else None
    return {"count": database.count_readings(since=since_text, until=until_text, source=source, status=status)}


@app.get("/readings/latest", response_model=Reading | None)
def get_latest(source: Source | None = None) -> dict | None:
    return database.fetch_latest(source=source)


@app.get("/anomalies", response_model=list[Reading])
def get_anomalies(
    days: int | None = Query(default=None, ge=1, le=3650),
    limit: int = Query(default=500, ge=1, le=1000),
    source: Source | None = None,
) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat() if days else None
    return database.fetch_readings(limit=limit, since=since, status="ANOMALY", source=source)


@app.get("/analytics")
def get_analytics(source: Source | None = None) -> dict:
    return database.analytics(source=source)


@app.get("/model/status", response_model=ModelStatus)
def get_model_status() -> dict:
    return detector.status()


@app.get("/datasets")
def get_datasets(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    return database.fetch_dataset_imports(limit=limit, offset=offset)


@app.post("/readings/import")
async def import_csv(file: UploadFile = File(...), source: ImportSource = "campus") -> dict:
    if not detector.available:
        raise HTTPException(status_code=503, detail="Train the model before importing readings.")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Upload a CSV file.")
    try:
        raw = await file.read(10_000_001)
        if len(raw) > 10_000_000:
            raise HTTPException(status_code=413, detail="CSV must be 10 MB or smaller.")
        raw_frame = pd.read_csv(BytesIO(raw))
        frame, errors, duplicate_rows = clean_dataset_with_report(raw_frame)
    except HTTPException:
        raise
    except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    readings: list[dict] = []
    if len(frame) > 1:
        deltas = frame["timestamp"].sort_values().diff().dt.total_seconds().dropna()
        positive_deltas = deltas[deltas > 0]
        import_interval_seconds = (
            float(positive_deltas.median())
            if not positive_deltas.empty
            else detector.sampling_interval_seconds
        )
    else:
        import_interval_seconds = detector.sampling_interval_seconds
    for row in frame.to_dict(orient="records"):
        try:
            timestamp = row["timestamp"].to_pydatetime()
            payload = ReadingInput(
                timestamp=timestamp,
                voltage=float(row["voltage"]),
                current=float(row["current"]),
                power=float(row["power"]),
                energy=float(row["energy"]),
                interval_seconds=import_interval_seconds,
            )
            calculated_power = payload.voltage * payload.current
            result = detector.score(
                payload.voltage,
                payload.current,
                calculated_power,
                payload.energy,
                payload.interval_seconds,
            )
            readings.append({
                "timestamp": payload.timestamp.astimezone(timezone.utc).isoformat(),
                "voltage": payload.voltage,
                "current": payload.current,
                "power": calculated_power,
                "energy": payload.energy,
                "interval_seconds": payload.interval_seconds or detector.sampling_interval_seconds,
                "cumulative_energy_kwh": None,
                "source": source,
                **result,
            })
        except (TypeError, ValueError) as exc:
            errors.append({"row": int(row.get("_csv_row", 0)), "error": str(exc)})

    try:
        report = database.save_dataset_import(
            filename=file.filename,
            source=source,
            total_rows=len(raw_frame),
            rows=readings,
            errors=errors,
            duplicate_rows=duplicate_rows,
        )
    except Exception as exc:
        logger.exception("CSV import transaction failed")
        raise HTTPException(status_code=503, detail="CSV import could not be stored.") from exc
    return report