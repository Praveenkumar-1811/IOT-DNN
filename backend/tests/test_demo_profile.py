import pytest

from backend.generate_demo_data import daily_baseline_current, generate


def test_daily_profile_reflects_building_operating_hours():
    assert daily_baseline_current(2) < daily_baseline_current(7)
    assert daily_baseline_current(7) < daily_baseline_current(10)
    assert daily_baseline_current(14) > daily_baseline_current(10)
    assert daily_baseline_current(19) > daily_baseline_current(22)


def test_generated_demo_energy_uses_five_second_kwh_increment(tmp_path):
    import pandas as pd

    output = generate(tmp_path / "demo_energy_data.csv", samples=12)
    frame = pd.read_csv(output)
    expected = frame["power"] * 5 / 3_600_000
    assert (frame["energy"] - expected).abs().max() < 1e-12
    assert frame["current"].between(0.8, 4.8).all()
    assert frame["timestamp"].is_monotonic_increasing