import json
import logging
import math
import os
from pathlib import Path

import joblib
import numpy as np

from backend.preprocessing import FEATURES, feature_vector

logger = logging.getLogger(__name__)
ARTIFACT_DIR = Path(os.getenv("MODEL_DIR", Path(__file__).parent))
MODEL_PATH = ARTIFACT_DIR / "energy_autoencoder.keras"
SCALER_PATH = ARTIFACT_DIR / "scaler.pkl"
THRESHOLD_PATH = ARTIFACT_DIR / "threshold.txt"
METADATA_PATH = ARTIFACT_DIR / "model_metadata.json"


class AutoencoderDetector:
    def __init__(self) -> None:
        self.model = None
        self.scaler = None
        self.threshold: float | None = None
        self.metadata: dict = {}
        self.load()

    @property
    def available(self) -> bool:
        return self.model is not None and self.scaler is not None and self.threshold is not None

    @property
    def sampling_interval_seconds(self) -> float:
        return float(self.metadata.get("sampling_interval_seconds", 5))

    def load(self) -> None:
        required_paths = (MODEL_PATH, SCALER_PATH, THRESHOLD_PATH)
        missing_paths = [str(path) for path in required_paths if not path.exists()]
        if missing_paths:
            self.metadata = {"load_error": f"Missing model artifact(s): {', '.join(missing_paths)}"}
            return
        try:
            import tensorflow as tf

            self.model = tf.keras.models.load_model(MODEL_PATH, compile=False)
            self.scaler = joblib.load(SCALER_PATH)
            self.threshold = float(THRESHOLD_PATH.read_text(encoding="utf-8").strip())
            if not math.isfinite(self.threshold) or self.threshold <= 0:
                raise ValueError("Model threshold must be a finite positive number")
            if METADATA_PATH.exists():
                self.metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            self.model = self.scaler = self.threshold = None
            self.metadata = {"load_error": str(exc)}
            logger.exception("Failed to load trained model artifacts from %s", ARTIFACT_DIR)

    def score(
        self,
        voltage: float,
        current: float,
        power: float,
        energy: float,
        interval_seconds: float | None = None,
    ) -> dict:
        if not self.available:
            raise RuntimeError("Trained model artifacts are missing or could not be loaded")
        observed_interval = interval_seconds or self.sampling_interval_seconds
        normalized_energy = energy * self.sampling_interval_seconds / observed_interval
        values = feature_vector(voltage, current, power, normalized_energy)
        scaled = self.scaler.transform(values)
        reconstructed = self.model.predict(scaled, verbose=0)
        score = float(np.mean(np.square(scaled - reconstructed)))
        threshold = float(self.threshold)
        if not math.isfinite(score):
            raise RuntimeError("Autoencoder produced a non-finite reconstruction score")
        ratio = score / max(threshold, 1e-12)
        if score <= threshold:
            status, severity = "NORMAL", "LOW"
        else:
            status = "ANOMALY"
            severity = "MEDIUM" if ratio < 1.5 else "HIGH" if ratio < 3 else "CRITICAL"
        return {
            "anomaly_score": score,
            "threshold": threshold,
            "model_version": str(self.metadata.get("last_trained_at", "unknown")),
            "status": status,
            "severity": severity,
        }

    def status(self) -> dict:
        message = "Model ready"
        if not self.available:
            message = self.metadata.get(
                "load_error",
                "Trained model artifacts are missing or could not be loaded. Run backend/train.py after checking the artifact paths.",
            )
        return {
            "available": self.available,
            "threshold": self.threshold,
            "sampling_interval_seconds": self.sampling_interval_seconds,
            "threshold_percentile": float(os.getenv("THRESHOLD_PERCENTILE", "95")),
            "training_samples": int(self.metadata.get("training_samples", 0)),
            "last_trained_at": self.metadata.get("last_trained_at"),
            "message": message,
        }