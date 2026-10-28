import pandas as pd
import pytest

from backend.prepare_bdg2 import prepare_bdg2


def test_prepare_bdg2_wide_electricity_file_marks_derived_fields(tmp_path):
    source = tmp_path / "electricity.csv"
    output = tmp_path / "normalized.csv"
    pd.DataFrame({
        "timestamp": ["2016-01-01 00:00:00", "2016-01-01 01:00:00"],
        "building_1": [2.3, 4.6],
    }).to_csv(source, index=False)

    metadata = prepare_bdg2(source, output)
    converted = pd.read_csv(output)

    assert metadata["source"] == "Building Data Genome Project 2"
    assert "not measured" in metadata["voltage_and_current"]
    assert converted.loc[0, "power"] == pytest.approx(2300)
    assert converted.loc[0, "current"] == pytest.approx(10)
    assert converted.loc[0, "energy"] == pytest.approx(2.3)


def test_prepare_bdg2_long_format_filters_building_and_meter(tmp_path):
    source = tmp_path / "meters.csv"
    output = tmp_path / "selected.csv"
    pd.DataFrame({
        "timestamp": ["2016-01-01T00:00:00Z", "2016-01-01T00:00:00Z"],
        "building_id": ["a", "b"],
        "meter": ["electricity", "electricity"],
        "meter_reading": [1.2, 9.5],
    }).to_csv(source, index=False)

    prepare_bdg2(source, output, building_id="a")
    converted = pd.read_csv(output)
    assert len(converted) == 1
    assert converted.loc[0, "energy"] == pytest.approx(1.2)


def test_prepare_bdg2_requires_meter_for_ambiguous_wide_file(tmp_path):
    source = tmp_path / "wide.csv"
    pd.DataFrame({"timestamp": ["2016-01-01"], "a": [1], "b": [2]}).to_csv(source, index=False)
    with pytest.raises(ValueError, match="meter-column"):
        prepare_bdg2(source, tmp_path / "out.csv")