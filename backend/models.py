from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ReadingRecord(Base):
    __tablename__ = "readings"
    __table_args__ = (
        CheckConstraint("voltage > 0"),
        CheckConstraint("current >= 0"),
        CheckConstraint("power >= 0"),
        CheckConstraint("energy >= 0"),
        CheckConstraint("status IN ('NORMAL', 'ANOMALY')"),
        CheckConstraint("severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[str] = mapped_column(String, index=True)
    voltage: Mapped[float] = mapped_column(Float)
    current: Mapped[float] = mapped_column(Float)
    power: Mapped[float] = mapped_column(Float)
    energy: Mapped[float] = mapped_column(Float)
    interval_seconds: Mapped[float] = mapped_column(Float, default=5)
    cumulative_energy_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    anomaly_score: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String, default="unknown")
    source: Mapped[str] = mapped_column(String, default="live", index=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_source: Mapped[str | None] = mapped_column(String, nullable=True)
    device_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True)
    severity: Mapped[str] = mapped_column(String)
    import_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_imports.id"), nullable=True)
    dataset_import: Mapped["DatasetImport | None"] = relationship(back_populates="readings")


class DatasetImport(Base):
    __tablename__ = "dataset_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, index=True)
    imported_at: Mapped[str] = mapped_column(
        String, default=lambda: datetime.now(timezone.utc).isoformat()
    )
    total_rows: Mapped[int] = mapped_column(Integer)
    accepted_rows: Mapped[int] = mapped_column(Integer)
    rejected_rows: Mapped[int] = mapped_column(Integer)
    duplicate_rows: Mapped[int] = mapped_column(Integer)
    errors_json: Mapped[str] = mapped_column(Text, default="[]")
    readings: Mapped[list[ReadingRecord]] = relationship(back_populates="dataset_import")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class ModelMetadata(Base):
    __tablename__ = "model_metadata"

    version: Mapped[str] = mapped_column(String, primary_key=True)
    training_data: Mapped[str] = mapped_column(String)
    features_json: Mapped[str] = mapped_column(Text)
    trained_at: Mapped[str] = mapped_column(String)
    configuration_json: Mapped[str] = mapped_column(Text)
