import numpy as np
import pytest

from backend.train import chronological_partitions


def test_chronological_split_keeps_test_labels_aligned_and_trains_on_normals_only():
    values = np.arange(100, dtype=np.float32).reshape(-1, 1)
    anomaly_mask = np.zeros(100, dtype=bool)
    anomaly_mask[[10, 70, 90]] = True

    train, calibration, test, train_end, calibration_end, excluded = chronological_partitions(values, anomaly_mask)

    assert train_end == 60
    assert calibration_end == 80
    assert 10 not in train
    assert 70 not in calibration
    assert test[0, 0] == 80
    assert test[-1, 0] == 99
    assert excluded == 2


def test_chronological_split_rejects_misaligned_labels():
    with pytest.raises(ValueError, match="matching row counts"):
        chronological_partitions(np.zeros((5, 4)), np.zeros(4, dtype=bool))