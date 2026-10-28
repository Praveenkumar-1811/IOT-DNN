import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.preprocessing import StandardScaler
from tensorflow.keras import Sequential
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.layers import Dense, Input

from backend.preprocessing import FEATURES, clean_dataset, find_label_column, labels_are_anomalies

ROOT = Path(__file__).parent
DATA_PATH = Path(os.getenv("TRAINING_DATA", ROOT / "data" / "demo_energy_data.csv"))
MODEL_PATH = Path(os.getenv("MODEL_DIR", ROOT))


def chronological_partitions(values: np.ndarray, anomaly_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int, int]:
    if values.ndim != 2 or anomaly_mask.shape != (len(values),):
        raise ValueError("Values and anomaly labels must have matching row counts")
    train_end = max(int(len(values) * 0.6), 1)
    validation_end = max(int(len(values) * 0.8), train_end + 1)
    train_values = values[:train_end][~anomaly_mask[:train_end]]
    calibration_values = values[train_end:validation_end][~anomaly_mask[train_end:validation_end]]
    test_values = values[validation_end:]
    excluded_anomalies = int(anomaly_mask[:validation_end].sum())
    return train_values, calibration_values, test_values, train_end, validation_end, excluded_anomalies


def build_model() -> tf.keras.Model:
    model = Sequential([
        Input(shape=(len(FEATURES),)),
        Dense(16, activation="relu"),
        Dense(8, activation="relu"),
        Dense(4, activation="relu"),
        Dense(8, activation="relu"),
        Dense(16, activation="relu"),
        Dense(len(FEATURES), activation="linear"),
    ])
    model.compile(optimizer="adam", loss="mse")
    return model


def train() -> None:
    percentile = float(os.getenv("THRESHOLD_PERCENTILE", "95"))
    if not 50 <= percentile < 100:
        raise ValueError("THRESHOLD_PERCENTILE must be at least 50 and less than 100")
    raw = pd.read_csv(DATA_PATH)
    frame = clean_dataset(raw)
    label_column = find_label_column(frame)
    anomaly_mask = np.zeros(len(frame), dtype=bool)
    if label_column:
        anomaly_mask = labels_are_anomalies(frame[label_column])
    if len(frame) < 50:
        raise ValueError("Training data needs at least 50 valid chronological readings")

    values = frame[FEATURES].to_numpy(dtype=np.float32)
    train_values, validation_values, test_values, train_end, validation_end, excluded_anomalies = chronological_partitions(values, anomaly_mask)
    if len(validation_values) < 2 or len(test_values) < 2:
        raise ValueError("Training data needs at least 10 readings for validation and test partitions")
    if len(train_values) < 50:
        raise ValueError("Training data needs at least 50 normal readings in the first 60 percent")
    timestamp_deltas = frame["timestamp"].sort_values().diff().dt.total_seconds().dropna()
    positive_deltas = timestamp_deltas[timestamp_deltas > 0]
    sampling_interval_seconds = float(positive_deltas.median()) if not positive_deltas.empty else 5.0
    scaler = StandardScaler().fit(train_values)
    train_scaled = scaler.transform(train_values)
    validation_scaled = scaler.transform(validation_values)

    tf.keras.utils.set_random_seed(42)
    model = build_model()
    model.fit(
        train_scaled,
        train_scaled,
        validation_data=(validation_scaled, validation_scaled),
        epochs=150,
        batch_size=32,
        callbacks=[EarlyStopping(monitor="val_loss", patience=12, restore_best_weights=True)],
        verbose=1,
    )
    reconstructed = model.predict(validation_scaled, verbose=0)
    errors = np.mean(np.square(validation_scaled - reconstructed), axis=1)
    raw_threshold = float(np.percentile(errors, percentile))
    # Use a small, explicit safety margin above the raw validation cutoff so the
    # model remains stable on legitimate building loads while still catching true
    # faults with a wide margin.
    THRESHOLD_MARGIN = 1.35
    threshold = raw_threshold * THRESHOLD_MARGIN if raw_threshold > 0 else 1e-6

    MODEL_PATH.mkdir(parents=True, exist_ok=True)
    model.save(MODEL_PATH / "energy_autoencoder.keras")
    joblib.dump(scaler, MODEL_PATH / "scaler.pkl")
    (MODEL_PATH / "threshold.txt").write_text(f"{threshold:.12g}\n", encoding="utf-8")
    metadata = {
        "training_samples": len(train_values),
        "validation_samples": len(validation_values),
        "test_samples": len(test_values),
        "split_method": "chronological 60/20/20 train/calibration/test",
        "ground_truth_column": label_column,
        "excluded_labeled_anomalies_from_training_and_calibration": excluded_anomalies,
        "chronological_train_end_row": train_end,
        "chronological_calibration_end_row": validation_end,
        "normal_only_training": True,
        "last_trained_at": datetime.now(timezone.utc).isoformat(),
        "threshold_percentile": percentile,
        "threshold": threshold,
        "sampling_interval_seconds": sampling_interval_seconds,
        "raw_threshold": raw_threshold,
        "validation_error_mean": float(errors.mean()),
        "validation_error_max": float(errors.max()),
        "training_data": str(DATA_PATH),
        "data_classification": "generated demo-normal dataset" if "demo" in DATA_PATH.name.lower() else "user-provided dataset",
    }
    (MODEL_PATH / "model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    train()