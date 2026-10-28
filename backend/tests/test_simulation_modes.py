import pytest

from backend.detector import AutoencoderDetector, THRESHOLD_PATH


@pytest.fixture(scope="module")
def detector():
    result = AutoencoderDetector()
    if not result.available:
        pytest.skip("Train the Autoencoder before testing simulation classifications")
    return result


def test_normal_software_reading_stays_normal(detector):
    result = detector.score(230.0, 2.5, 575.0, 575.0 * 5 / 3_600_000)
    assert result["status"] == "NORMAL"
    assert result["anomaly_score"] <= result["threshold"]


def test_detector_uses_threshold_saved_by_training(detector):
    saved_threshold = float(THRESHOLD_PATH.read_text(encoding="utf-8").strip())
    assert detector.threshold == saved_threshold


def test_one_second_energy_is_normalized_to_training_interval(detector):
    current = 2.5
    power = 230.0 * current
    energy = power / 3_600_000
    result = detector.score(230.0, current, power, energy, interval_seconds=1)
    assert result["status"] == "NORMAL"


@pytest.mark.parametrize("voltage,current", [
    (230.0, 10.0),
    (230.0, 10.5),
    (230.0, 11.5),
    (180.0, 2.8),
    (240.0, 0.7),
])
def test_abnormal_software_modes_exceed_learned_threshold(detector, voltage, current):
    power = voltage * current
    result = detector.score(voltage, current, power, power * 5 / 3_600_000)
    assert result["status"] == "ANOMALY"
    assert result["anomaly_score"] > result["threshold"]