import numpy as np
import pandas as pd

from backend.experiments.moment_comparison import WINDOW, label_vector, metrics, windows


def test_moment_windows_keep_complete_context_and_overlap():
    values = np.arange(640, dtype=np.float32).reshape(-1, 1)
    batches, starts = windows(values)
    assert batches.shape == (2, WINDOW, 1)
    assert starts == [0, 128]
    assert batches[-1, -1, 0] == 639


def test_moment_label_detection_and_confusion_metrics_are_truthful():
    frame = pd.DataFrame({"ground_truth": [0, 0, 1, 1]})
    name, labels = label_vector(frame)
    result = metrics(np.array([0.1, 0.2, 0.9, 0.8]), threshold=0.5, labels=labels)
    assert name == "ground_truth"
    assert result["confusion_matrix_tn_fp_fn_tp"] == [2, 0, 0, 2]
    assert result["f1"] == 1


def test_unlabeled_moment_results_omit_classification_metrics():
    result = metrics(np.array([0.1, 0.2]), threshold=0.15, labels=None)
    assert result["ground_truth_available"] is False
    assert "precision" not in result
    assert result["flagged"] == 1