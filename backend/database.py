import json
import logging
import os
import re
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from sqlalchemy import MetaData, URL, case, create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable
from sqlalchemy.pool import NullPool

from backend.models import AppSetting, Base, DatasetImport, ModelMetadata, ReadingRecord


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).parent / "energy.db"))
logger = logging.getLogger(__name__)


@contextmanager
def session_scope() -> Iterator[Session]:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite", database=str(DATABASE_PATH)),
        connect_args={"timeout": 10},
        poolclass=NullPool,
    )
    try:
        with Session(engine, expire_on_commit=False) as session:
            with session.begin():
                yield session
    finally:
        engine.dispose()


def initialize_database() -> None:
    with session_scope() as session:
        Base.metadata.create_all(session.get_bind())
        columns = {column["name"] for column in inspect(session.get_bind()).get_columns("readings")}
        if "source" not in columns:
            session.execute(text("ALTER TABLE readings ADD COLUMN source TEXT NOT NULL DEFAULT 'live'"))
        if "cumulative_energy_kwh" not in columns:
            session.execute(text("ALTER TABLE readings ADD COLUMN cumulative_energy_kwh REAL"))
        if "import_id" not in columns:
            session.execute(text("ALTER TABLE readings ADD COLUMN import_id INTEGER REFERENCES dataset_imports(id)"))
        if "model_version" not in columns:
            session.execute(text("ALTER TABLE readings ADD COLUMN model_version TEXT NOT NULL DEFAULT 'unknown'"))
        if "interval_seconds" not in columns:
            session.execute(text("ALTER TABLE readings ADD COLUMN interval_seconds REAL NOT NULL DEFAULT 5"))
        if "data_source" not in columns:
            session.execute(text("ALTER TABLE readings ADD COLUMN data_source TEXT"))
        if "device_id" not in columns:
            session.execute(text("ALTER TABLE readings ADD COLUMN device_id TEXT"))
        if "request_id" not in columns:
            session.execute(text("ALTER TABLE readings ADD COLUMN request_id TEXT"))
        table_sql = session.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'readings'")
        ).scalar_one_or_none()
        has_legacy_source_check = (
            table_sql is not None
            and re.search(r"CHECK\s*\(\s*source\s+IN\b", table_sql, re.IGNORECASE) is not None
            and "wokwi_simulation" not in table_sql.lower()
        )
        if has_legacy_source_check:
            # SQLite cannot drop this CHECK constraint in place; rebuild while copying every row.
            metadata = MetaData()
            for table in Base.metadata.sorted_tables:
                table.to_metadata(
                    metadata,
                    name="readings_rebuild" if table.name == "readings" else None,
                )
            replacement = metadata.tables["readings_rebuild"]
            connection = session.connection()
            previous_count = session.execute(text("SELECT COUNT(*) FROM readings")).scalar_one()
            connection.execute(CreateTable(replacement))
            column_names = ", ".join(f'"{column.name}"' for column in ReadingRecord.__table__.columns)
            copied = connection.execute(text(
                f"INSERT INTO readings_rebuild ({column_names}) "
                f"SELECT {column_names} FROM readings"
            ))
            if copied.rowcount != previous_count:
                raise RuntimeError(
                    f"SQLite migration copied {copied.rowcount} of {previous_count} readings"
                )
            session.execute(text("DROP TABLE readings"))
            session.execute(text("ALTER TABLE readings_rebuild RENAME TO readings"))
            logger.info("Migrated legacy readings source constraint; preserved %d rows", previous_count)
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp)"))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_readings_status ON readings(status)"))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_readings_source ON readings(source)"))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_readings_import_id ON readings(import_id)"))
        session.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_readings_request_id "
            "ON readings(request_id) WHERE request_id IS NOT NULL"
        ))


def check_health() -> bool:
    with session_scope() as session:
        session.execute(text("SELECT 1"))
    return True


def _reading_dict(reading: ReadingRecord) -> dict:
    result = {
        name: getattr(reading, name)
        for name in (
            "id", "timestamp", "voltage", "current", "power", "energy", "interval_seconds",
            "interval_energy_kwh", "cumulative_energy_kwh", "anomaly_score", "threshold",
            "source", "data_source", "device_id", "request_id", "status", "severity", "import_id", "model_version",
        )
        if name != "interval_energy_kwh"
    }
    result["interval_energy_kwh"] = reading.energy
    return result


def insert_reading(reading: dict) -> dict:
    request_id = reading.get("request_id")
    if request_id:
        with session_scope() as session:
            existing = session.scalar(
                select(ReadingRecord).where(ReadingRecord.request_id == request_id)
            )
            if existing:
                return _reading_dict(existing)
    try:
        with session_scope() as session:
            record = ReadingRecord(**reading)
            session.add(record)
            session.flush()
            return _reading_dict(record)
    except IntegrityError:
        if request_id:
            with session_scope() as session:
                existing = session.scalar(
                    select(ReadingRecord).where(ReadingRecord.request_id == request_id)
                )
                if existing:
                    return _reading_dict(existing)
        raise


def save_dataset_import(
    filename: str,
    source: str,
    total_rows: int,
    rows: list[dict],
    errors: list[dict],
    duplicate_rows: int,
) -> dict:
    with session_scope() as session:
        record = DatasetImport(
            filename=filename,
            source=source,
            total_rows=total_rows,
            accepted_rows=len(rows),
            rejected_rows=total_rows - len(rows) - duplicate_rows,
            duplicate_rows=duplicate_rows,
            errors_json=json.dumps(errors[:100]),
        )
        session.add(record)
        session.flush()
        for row in rows:
            session.add(ReadingRecord(**row, import_id=record.id))
        session.flush()
        return dataset_import_dict(record)


def dataset_import_dict(record: DatasetImport) -> dict:
    return {
        "id": record.id,
        "filename": record.filename,
        "source": record.source,
        "imported_at": record.imported_at,
        "total_rows": record.total_rows,
        "accepted_rows": record.accepted_rows,
        "imported": record.accepted_rows,
        "rejected_rows": record.rejected_rows,
        "duplicate_rows": record.duplicate_rows,
        "errors": json.loads(record.errors_json),
    }


def fetch_dataset_imports(limit: int = 100, offset: int = 0) -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(
            select(DatasetImport).order_by(DatasetImport.id.desc()).offset(offset).limit(limit)
        ).all()
        return [dataset_import_dict(row) for row in rows]


def fetch_readings(
    limit: int = 100,
    since: str | None = None,
    status: str | None = None,
    source: str | None = None,
    offset: int = 0,
    until: str | None = None,
) -> list[dict]:
    query = select(ReadingRecord)
    if since:
        query = query.where(ReadingRecord.timestamp >= since)
    if until:
        query = query.where(ReadingRecord.timestamp <= until)
    if status:
        query = query.where(ReadingRecord.status == status)
    if source:
        query = query.where(ReadingRecord.source == source)
    query = query.order_by(ReadingRecord.timestamp.desc(), ReadingRecord.id.desc()).offset(offset).limit(limit)
    with session_scope() as session:
        return [_reading_dict(row) for row in session.scalars(query).all()]


def count_readings(
    since: str | None = None,
    status: str | None = None,
    source: str | None = None,
    until: str | None = None,
) -> int:
    query = select(func.count(ReadingRecord.id))
    if since:
        query = query.where(ReadingRecord.timestamp >= since)
    if until:
        query = query.where(ReadingRecord.timestamp <= until)
    if status:
        query = query.where(ReadingRecord.status == status)
    if source:
        query = query.where(ReadingRecord.source == source)
    with session_scope() as session:
        return int(session.scalar(query) or 0)


def fetch_latest(source: str | None = None) -> dict | None:
    query = select(ReadingRecord)
    if source:
        query = query.where(ReadingRecord.source == source)
    query = query.order_by(ReadingRecord.timestamp.desc(), ReadingRecord.id.desc()).limit(1)
    with session_scope() as session:
        row = session.scalar(query)
        return _reading_dict(row) if row else None


def analytics(source: str | None = None) -> dict:
    totals_query = select(
        func.count(ReadingRecord.id).label("reading_count"),
        func.coalesce(func.sum(ReadingRecord.energy), 0).label("total_energy"),
        func.coalesce(func.avg(ReadingRecord.energy), 0).label("average_energy"),
        func.coalesce(func.avg(ReadingRecord.power), 0).label("average_power"),
        func.coalesce(func.min(ReadingRecord.power), 0).label("minimum_power"),
        func.coalesce(func.max(ReadingRecord.power), 0).label("peak_power"),
        func.coalesce(func.avg(ReadingRecord.current), 0).label("average_current"),
        func.coalesce(func.sum(case((ReadingRecord.status == "ANOMALY", 1), else_=0)), 0).label("anomaly_count"),
    )
    daily_query = select(
        func.substr(ReadingRecord.timestamp, 1, 10).label("day"),
        func.sum(ReadingRecord.energy).label("energy"),
        func.avg(ReadingRecord.power).label("average_power"),
        func.min(ReadingRecord.power).label("minimum_power"),
        func.max(ReadingRecord.power).label("peak_power"),
        func.count(ReadingRecord.id).label("reading_count"),
        func.sum(case((ReadingRecord.status == "ANOMALY", 1), else_=0)).label("anomaly_count"),
    )
    source_query = select(
        ReadingRecord.source,
        func.count(ReadingRecord.id).label("reading_count"),
        func.sum(ReadingRecord.energy).label("total_energy"),
        func.sum(case((ReadingRecord.status == "ANOMALY", 1), else_=0)).label("anomaly_count"),
    )
    if source:
        totals_query = totals_query.where(ReadingRecord.source == source)
        daily_query = daily_query.where(ReadingRecord.source == source)
        source_query = source_query.where(ReadingRecord.source == source)
    with session_scope() as session:
        totals = dict(session.execute(totals_query).mappings().one())
        daily = [
            dict(row)
            for row in session.execute(
                daily_query.group_by("day").order_by("day")
            ).mappings().all()
        ]
        source_rows = session.execute(source_query.group_by(ReadingRecord.source)).all()

    result = {
        **totals,
        "anomaly_percentage": 100 * totals["anomaly_count"] / totals["reading_count"] if totals["reading_count"] else 0,
        "daily": daily,
        "weekly": _aggregate_periods(daily),
        "monthly": _aggregate_months(daily),
        "sources": [
            {
                "source": row.source,
                "reading_count": row.reading_count,
                "total_energy": row.total_energy or 0,
                "anomaly_count": row.anomaly_count or 0,
            }
            for row in source_rows
        ],
    }
    return result


def get_setting(key: str, default: str) -> str:
    with session_scope() as session:
        value = session.get(AppSetting, key)
        return value.value if value else default


def set_setting(key: str, value: str) -> None:
    with session_scope() as session:
        setting = session.get(AppSetting, key)
        if setting is None:
            setting = AppSetting(key=key, value=value)
            session.add(setting)
        else:
            setting.value = value


def save_model_metadata(version: str, training_data: str, features: list[dict[str, str]], trained_at: str, configuration: dict) -> None:
    with session_scope() as session:
        record = session.get(ModelMetadata, version)
        values = {
            "training_data": training_data,
            "features_json": json.dumps(features),
            "trained_at": trained_at,
            "configuration_json": json.dumps(configuration),
        }
        if record is None:
            session.add(ModelMetadata(version=version, **values))
        else:
            for key, value in values.items():
                setattr(record, key, value)


def _aggregate_periods(daily: list[dict]) -> list[dict]:
    buckets: dict[str, dict] = {}
    for row in daily:
        day = date.fromisoformat(row["day"])
        week_start = date.fromordinal(day.toordinal() - day.weekday())
        key = f"Week of {week_start.isoformat()}"
        bucket = buckets.setdefault(key, {"period": key, "energy": 0.0, "reading_count": 0})
        bucket["energy"] += row["energy"]
        bucket["reading_count"] += row["reading_count"]
    return list(buckets.values())


def _aggregate_months(daily: list[dict]) -> list[dict]:
    buckets: dict[str, dict] = {}
    for row in daily:
        key = row["day"][:7]
        bucket = buckets.setdefault(key, {"period": key, "energy": 0.0, "reading_count": 0})
        bucket["energy"] += row["energy"]
        bucket["reading_count"] += row["reading_count"]
    return list(buckets.values())
