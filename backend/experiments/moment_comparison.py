"""Compare the saved autoencoder with zero-shot MOMENT reconstruction."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from backend.detector import AutoencoderDetector
from backend.preprocessing import FEATURES, clean_dataset, find_label_column, labels_are_anomalies

WINDOW = 512
STRIDE = 128


def windows(values: np.ndarray, stride: int = STRIDE) -> tuple[np.ndarray, list[int]]:
    if len(values) < WINDOW:
        raise ValueError(f"MOMENT needs at least {WINDOW} timestamps; got {len(values)}")
    starts = list(range(0, len(values) - WINDOW + 1, stride))
    if starts[-1] != len(values) - WINDOW:
        starts.append(len(values) - WINDOW)
    samples = np.stack([values[start:start + WINDOW] for start in starts])
    return samples, starts


def moment_errors(model, values: np.ndarray, device: str, batch_size: int = 16) -> tuple[np.ndarray, float]:
    import torch

    samples, starts = windows(values)
    feature_count = values.shape[1]
    flattened = samples.transpose(0, 2, 1).reshape(-1, 1, WINDOW)
    reconstructed = np.empty_like(flattened, dtype=np.float32)
    model = model.to(device).float().eval()
    started = time.perf_counter()
    with torch.inference_mode():
        for offset in range(0, len(flattened), batch_size):
            batch = torch.as_tensor(flattened[offset:offset + batch_size], dtype=torch.float32, device=device)
            output = model(x_enc=batch)
            reconstructed[offset:offset + len(batch)] = output.reconstruction.detach().float().cpu().numpy()
    elapsed = time.perf_counter() - started

    reconstructed = reconstructed.reshape(len(samples), feature_count, 1, WINDOW).transpose(0, 3, 1, 2).squeeze(-1)
    sums = np.zeros_like(values, dtype=np.float64)
    counts = np.zeros_like(values, dtype=np.float64)
    for reconstruction, start in zip(reconstructed, starts, strict=True):
        sums[start:start + WINDOW] += reconstruction
        counts[start:start + WINDOW] += 1
    valid = counts[:, 0] > 0
    averaged = np.zeros_like(values, dtype=np.float64)
    averaged[valid] = sums[valid] / counts[valid]
    errors = np.mean(np.square(values - averaged), axis=1)
    return errors, elapsed


def label_vector(frame: pd.DataFrame) -> tuple[str | None, np.ndarray | None]:
    name = find_label_column(frame)
    if name is None:
        return None, None
    return name, labels_are_anomalies(frame[name])


def metrics(errors: np.ndarray, threshold: float, labels: np.ndarray | None) -> dict:
    predicted = errors > threshold
    result = {
        "threshold": float(threshold),
        "flagged": int(predicted.sum()),
        "flagged_percentage": float(predicted.mean() * 100) if len(predicted) else 0.0,
        "error_mean": float(np.mean(errors)),
        "error_median": float(np.median(errors)),
        "error_p95": float(np.percentile(errors, 95)),
        "error_max": float(np.max(errors)),
        "ground_truth_available": labels is not None,
    }
    if labels is not None:
        from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

        result.update({
            "accuracy": float(accuracy_score(labels, predicted)),
            "precision": float(precision_score(labels, predicted, zero_division=0)),
            "recall": float(recall_score(labels, predicted, zero_division=0)),
            "f1": float(f1_score(labels, predicted, zero_division=0)),
            "confusion_matrix_tn_fp_fn_tp": confusion_matrix(labels, predicted, labels=[False, True]).ravel().tolist(),
        })
    return result


def run(csv_path: Path, output_path: Path, checkpoint: str, threshold_percentile: float, device: str, batch_size: int) -> dict:
    raw = pd.read_csv(csv_path)
    frame = clean_dataset(raw)
    label_name, labels = label_vector(frame)
    if len(frame) < 854:
        raise ValueError("MOMENT comparison needs at least 854 clean chronological observations so its 60-percent training partition contains a full 512-step window")
    train_end = max(int(len(frame) * 0.6), 1)
    validation_end = max(int(len(frame) * 0.8), train_end + 1)
    feature_values = frame[FEATURES].to_numpy(dtype=np.float32)

    detector = AutoencoderDetector()
    if not detector.available:
        raise RuntimeError("Autoencoder artifacts missing; run python -m backend.train first")
    metadata_data = detector.metadata.get("training_data")
    if metadata_data and Path(metadata_data).resolve() != csv_path.resolve():
        raise RuntimeError("Set TRAINING_DATA to this CSV and retrain. The saved autoencoder uses the first 80%; this experiment evaluates only its final 20%.")
    scaled_values = detector.scaler.transform(feature_values)
    started = time.perf_counter()
    reconstructed = detector.model.predict(scaled_values[validation_end:], batch_size=256, verbose=0)
    autoencoder_seconds = time.perf_counter() - started
    autoencoder_errors = np.mean(np.square(scaled_values[validation_end:] - reconstructed), axis=1)

    try:
        from momentfm import MOMENTPipeline
        import torch
    except ImportError as exc:
        raise RuntimeError("Optional dependencies missing. Install backend/experiments/requirements-moment.txt") from exc
    model = MOMENTPipeline.from_pretrained(checkpoint, model_kwargs={"task_name": "reconstruction"})
    model.init()
    train_context_errors, moment_train_seconds = moment_errors(model, scaled_values[:train_end], device, batch_size)
    calibration_start = train_end - WINDOW + 1
    calibration_context_errors, moment_calibration_seconds = moment_errors(
        model,
        scaled_values[calibration_start:validation_end],
        device,
        batch_size,
    )
    calibration_errors = calibration_context_errors[-(validation_end - train_end):]
    context_start = validation_end - WINDOW + 1
    test_context_errors, moment_test_seconds = moment_errors(model, scaled_values[context_start:], device, batch_size)
    test_errors = test_context_errors[-(len(frame) - validation_end):]
    if labels is not None and len(labels) == len(frame):
        calibration_errors = calibration_errors[~labels[train_end:validation_end]]
    if not len(calibration_errors):
        raise ValueError("MOMENT has no normal calibration errors for threshold calibration")

    eval_labels = labels[validation_end:] if labels is not None and len(labels) == len(frame) else None
    result = {
        "dataset": str(csv_path.resolve()),
        "rows": len(frame),
        "split": {"method": "chronological 60/20/20", "train_rows": train_end, "calibration_rows": validation_end - train_end, "test_rows": len(frame) - validation_end},
        "ground_truth_column": label_name,
        "evaluation_limitations": None if eval_labels is not None else "No supported ground-truth label column; precision, recall, F1, accuracy, and confusion matrix are not reported.",
        "autoencoder": {
            **metrics(autoencoder_errors, float(detector.threshold), eval_labels),
            "threshold_source": "saved middle-20-percent normal calibration percentile",
            "inference_seconds": autoencoder_seconds,
        },
        "moment": {
            **metrics(test_errors, float(np.percentile(calibration_errors, threshold_percentile)), eval_labels),
            "checkpoint": checkpoint,
            "task": "zero-shot reconstruction",
            "threshold_source": f"{threshold_percentile}th percentile of MOMENT normal middle-20-percent calibration errors",
            "train_inference_seconds": moment_train_seconds,
            "calibration_inference_seconds": moment_calibration_seconds,
            "test_inference_seconds": moment_test_seconds,
            "device": device,
        },
        "reproducibility": {"window": WINDOW, "stride": STRIDE, "calibration_lookback_rows": WINDOW - 1, "test_lookback_rows": WINDOW - 1, "threshold_percentile": threshold_percentile, "split": "chronological 60/20/20"},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    def default_device() -> str:
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="Normalized, chronologically ordered project CSV")
    parser.add_argument("--output", type=Path, default=Path("backend/experiments/results/moment_comparison.json"))
    parser.add_argument("--checkpoint", default="AutonLab/MOMENT-1-small")
    parser.add_argument("--threshold-percentile", type=float, default=95.0)
    parser.add_argument("--device", default=default_device())
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    if not 50 <= args.threshold_percentile < 100:
        parser.error("--threshold-percentile must be in [50, 100)")
    run(args.csv, args.output, args.checkpoint, args.threshold_percentile, args.device, args.batch_size)


if __name__ == "__main__":
    main()