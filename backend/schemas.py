from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Source = Literal["live", "wokwi_simulation", "campus", "public_dataset", "demo"]
ImportSource = Literal["campus", "public_dataset", "demo"]


class ReadingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    voltage: float = Field(gt=0, le=1000)
    current: float = Field(ge=0, le=10_000)
    power: float | None = Field(default=None, ge=0, le=3_000_000)
    energy: float | None = Field(default=None, ge=0, le=10_000)
    interval_energy_kwh: float | None = Field(default=None, ge=0, le=10_000)
    interval_seconds: float | None = Field(default=None, gt=0, le=86_400)
    cumulative_energy_kwh: float | None = Field(default=None, ge=0, le=1_000_000)
    device_id: str | None = Field(default=None, min_length=1, max_length=64)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    data_source: Literal["wokwi_simulation"] | None = None

    @model_validator(mode="after")
    def validate_interval_energy(self):
        if self.energy is None and self.interval_energy_kwh is None:
            raise ValueError("Provide energy or interval_energy_kwh.")
        if self.energy is not None and self.interval_energy_kwh is not None:
            tolerance = max(1e-12, self.energy * 1e-6)
            if abs(self.energy - self.interval_energy_kwh) > tolerance:
                raise ValueError("energy and interval_energy_kwh must match when both are provided.")
        return self


class Reading(ReadingInput):
    id: int
    import_id: int | None = None
    model_version: str = "unknown"
    power: float
    energy: float
    interval_energy_kwh: float
    device_id: str | None = None
    request_id: str | None = None
    data_source: Literal["wokwi_simulation"] | None = None
    anomaly_score: float
    threshold: float
    source: Source = "live"
    status: Literal["NORMAL", "ANOMALY"]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class ModelStatus(BaseModel):
    available: bool
    name: str = "Deep Autoencoder"
    features: list[str] = ["voltage", "current", "power", "energy"]
    architecture: str = "Input → 16 → 8 → 4 → 8 → 16 → Output"
    loss: str = "Mean Squared Error"
    threshold: float | None
    sampling_interval_seconds: float = 5
    threshold_percentile: float
    training_samples: int
    last_trained_at: str | None
    message: str


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_replay_interval_seconds: int | None = Field(default=None, ge=1, le=3600)