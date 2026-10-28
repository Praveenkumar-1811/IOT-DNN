import sqlite3

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import database
from backend.main import app, detector
from backend.preprocessing import clean_dataset


@pytest.fixture(autouse=True)
def temporary_database(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test-energy.db")


def test_pipeline_requires_trained_model():
    if not detector.available:
        with TestClient(app) as client:
            response = client.post("/reading", json={"voltage": 230, "current": 2.5, "power": 575, "energy": 0.0008})
            assert response.status_code == 503


def test_health_and_model_status():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == ("ok" if detector.available else "degraded")
        status = client.get("/model/status").json()
        assert status["available"] is detector.available


def test_database_migrates_legacy_source_constraint_and_preserves_readings(tmp_path, monkeypatch):
    path = tmp_path / "legacy-energy.db"
    monkeypatch.setattr(database, "DATABASE_PATH", path)
    with sqlite3.connect(path) as connection:
        connection.execute("""
            CREATE TABLE readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                voltage REAL NOT NULL CHECK (voltage > 0),
                current REAL NOT NULL CHECK (current >= 0),
                power REAL NOT NULL CHECK (power >= 0),
                energy REAL NOT NULL CHECK (energy >= 0),
                anomaly_score REAL NOT NULL,
                threshold REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'live'
                    CHECK (source IN ('live', 'campus', 'public_dataset', 'demo')),
                status TEXT NOT NULL CHECK (status IN ('NORMAL', 'ANOMALY')),
                severity TEXT NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'))
            )
        """)
        connection.execute("""
            INSERT INTO readings
                (id, timestamp, voltage, current, power, energy, anomaly_score,
                 threshold, source, status, severity)
            VALUES (42, '2026-01-01T00:00:00+00:00', 230, 2.5, 575, 0.0008,
                    0.000001, 0.00001, 'live', 'NORMAL', 'LOW')
        """)

    database.initialize_database()
    with sqlite3.connect(path) as connection:
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'readings'"
        ).fetchone()[0]
        preserved = connection.execute(
            "SELECT id, source, timestamp FROM readings WHERE id = 42"
        ).fetchone()
        assert "CHECK (source IN" not in schema
        assert preserved == (42, "live", "2026-01-01T00:00:00+00:00")

    if detector.available:
        with TestClient(app) as client:
            response = client.post("/reading", json={
                "device_id": "wokwi-esp32-01",
                "voltage": 230,
                "current": 2.5,
                "interval_energy_kwh": 575 / 3_600_000,
                "interval_seconds": 1,
                "data_source": "wokwi_simulation",
                "request_id": "legacy-schema-migration-test",
            })
        assert response.status_code == 201, response.text
        assert response.json()["source"] == "wokwi_simulation"


def test_dataset_replay_is_separate_and_can_be_stopped():
    if not detector.available:
        pytest.skip("Train the Autoencoder before testing dataset replay")
    with TestClient(app) as client:
        status = client.get("/dataset-replay").json()
        assert status["running"]
        assert status["source"] == "demo"
        assert status["dataset"] == "demo_energy_data.csv"
        demo_readings = client.get("/readings?source=demo").json()
        assert demo_readings
        assert demo_readings[0]["status"] == "NORMAL"
        stopped = client.post("/dataset-replay/stop").json()
        assert stopped["running"] is False
        started = client.post("/dataset-replay/start").json()
        assert started["running"] is True
        client.post("/dataset-replay/stop")


def test_normal_and_outlier_readings_are_stored():
    if not detector.available:
        raise AssertionError("Run python -m backend.train before the model integration test")
    with TestClient(app) as client:
        normal = client.post("/reading", json={"voltage": 230, "current": 2.5, "power": 575, "energy": 0.0008})
        anomaly = client.post("/reading", json={"voltage": 230, "current": 18, "power": 4140, "energy": 0.00575})
        assert normal.status_code == 201, normal.text
        assert anomaly.status_code == 201, anomaly.text
        assert normal.json()["status"] == "NORMAL"
        assert normal.json()["model_version"]
        assert anomaly.json()["status"] == "ANOMALY"
        assert anomaly.json()["anomaly_score"] > anomaly.json()["threshold"]
        assert client.get("/readings/latest").json()["id"] == anomaly.json()["id"]
        assert len(client.get("/anomalies").json()) >= 1
        analytics = client.get("/analytics").json()
        assert analytics["reading_count"] >= 2
        assert analytics["anomaly_count"] >= 1


def test_one_second_live_energy_is_saved_and_scored_at_model_interval():
    if not detector.available:
        pytest.skip("Train the Autoencoder before testing live readings")
    power = 230 * 2.5
    with TestClient(app) as client:
        response = client.post("/reading?source=live", json={
            "voltage": 230,
            "current": 2.5,
            "power": power,
            "energy": power / 3_600_000,
            "interval_seconds": 1,
        })
    assert response.status_code == 201, response.text
    assert response.json()["interval_seconds"] == 1
    assert response.json()["status"] == "NORMAL"


def test_wokwi_payload_is_scored_stored_and_kept_as_simulation_source():
    if not detector.available:
        raise AssertionError("Run python -m backend.train before the model integration test")
    power = 230 * 2.5
    interval_energy = power / 3_600_000
    with TestClient(app) as client:
        response = client.post("/reading", json={
            "device_id": "wokwi-esp32-01",
            "timestamp": "2026-10-23T08:00:00Z",
            "voltage": 230,
            "current": 2.5,
            "power": power,
            "interval_energy_kwh": interval_energy,
            "interval_seconds": 1,
            "data_source": "wokwi_simulation",
            "request_id": "wokwi-esp32-01-idempotency-test",
        })
        assert response.status_code == 201, response.text
        reading = response.json()
        assert reading["source"] == reading["data_source"] == "wokwi_simulation"
        assert reading["device_id"] == "wokwi-esp32-01"
        assert reading["energy"] == reading["interval_energy_kwh"] == pytest.approx(interval_energy)
        assert reading["status"] == "NORMAL"
        assert reading["anomaly_score"] <= reading["threshold"]
        stored = client.get("/readings/latest?source=wokwi_simulation").json()
        assert stored["id"] == reading["id"]
        assert stored["device_id"] == reading["device_id"]
        duplicate = client.post("/reading", json={
            "device_id": "wokwi-esp32-01",
            "timestamp": "2026-10-23T08:00:00Z",
            "voltage": 230,
            "current": 2.5,
            "power": power,
            "interval_energy_kwh": interval_energy,
            "interval_seconds": 1,
            "data_source": "wokwi_simulation",
            "request_id": "wokwi-esp32-01-idempotency-test",
        })
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == reading["id"]
        assert client.get("/analytics?source=wokwi_simulation").json()["reading_count"] == 1


def test_inference_failure_is_reported_as_unavailable(monkeypatch):
    if not detector.available:
        pytest.skip("Train the Autoencoder before testing inference failure handling")

    def fail_inference(*_args, **_kwargs):
        raise RuntimeError("inference test failure")

    monkeypatch.setattr(detector, "score", fail_inference)
    with TestClient(app) as client:
        response = client.post("/reading", json={
            "voltage": 230,
            "current": 2.5,
            "interval_energy_kwh": 0.0001597222,
            "interval_seconds": 1,
        })
    assert response.status_code == 503
    assert response.json()["detail"] == "Autoencoder inference failed."


def test_invalid_reading_and_power_mismatch_are_rejected():
    with TestClient(app) as client:
        assert client.post("/reading", json={"voltage": -1, "current": 2, "energy": 0}).status_code == 422
        assert client.post("/reading", json={"voltage": 230, "current": "NaN", "energy": 0}).status_code == 422
        if detector.available:
            response = client.post("/reading", json={"voltage": 230, "current": 2.5, "power": 10, "energy": 0})
            assert response.status_code == 422
        assert client.post("/reading", json={
            "voltage": 230,
            "current": 2.5,
            "power": 575,
            "interval_energy_kwh": 0.001,
            "energy": 0.0001,
        }).status_code == 422
        assert client.post("/reading?source=campus", json={
            "voltage": 230,
            "current": 2.5,
            "interval_energy_kwh": 0.0001,
            "data_source": "wokwi_simulation",
        }).status_code == 422


def test_sources_are_kept_separate():
    if not detector.available:
        raise AssertionError("Run python -m backend.train before source-separation tests")
    payload = {"voltage": 230, "current": 2.5, "power": 575, "energy": 0.0008}
    with TestClient(app) as client:
        live = client.post("/reading", json=payload)
        campus = client.post("/reading?source=campus", json=payload)
        assert live.status_code == campus.status_code == 201
        assert live.json()["source"] == "live"
        assert campus.json()["source"] == "campus"
        assert len(client.get("/readings?source=live").json()) == 1
        assert len(client.get("/readings?source=campus").json()) == 1
        assert client.get("/analytics?source=campus").json()["reading_count"] == 1
        analytics = client.get("/analytics?source=campus").json()
        assert analytics["minimum_power"] == 575
        assert {item["source"] for item in analytics["sources"]} == {"campus"}
        all_sources = client.get("/analytics").json()["sources"]
        assert {item["source"] for item in all_sources}.issuperset({"demo", "live", "campus"})


def test_reading_pagination_and_utc_date_filters():
    if not detector.available:
        pytest.skip("Train the Autoencoder before testing reading ingestion")
    with TestClient(app) as client:
        for timestamp in ("2026-10-01T12:00:00Z", "2026-10-02T12:00:00Z"):
            response = client.post("/reading?source=live", json={
                "timestamp": timestamp,
                "voltage": 230,
                "current": 2.5,
                "energy": 0.0008,
            })
            assert response.status_code == 201, response.text
        query = "source=live&since=2026-10-02T00:00:00Z&until=2026-10-02T23:59:59Z"
        assert client.get(f"/readings?limit=1&offset=0&{query}").json()[0]["timestamp"].startswith("2026-10-02")
        assert client.get(f"/readings/count?{query}").json()["count"] == 1


def test_csv_import_scores_and_persists_as_selected_source():
    if not detector.available:
        raise AssertionError("Run python -m backend.train before CSV import tests")
    csv_data = b"timestamp,voltage,current,power,energy\n2026-01-01T00:00:00Z,230,2.5,575,0.0008\n"
    with TestClient(app) as client:
        response = client.post("/readings/import?source=campus", files={"file": ("readings.csv", csv_data, "text/csv")})
        assert response.status_code == 200, response.text
        assert response.json()["imported"] == 1
        assert client.get("/readings/latest?source=campus").json()["status"] == "NORMAL"
        assert client.get("/readings/latest?source=campus").json()["import_id"] == response.json()["id"]
        assert client.get("/datasets").json()[0]["accepted_rows"] == 1


def test_csv_import_reports_invalid_and_duplicate_rows():
    if not detector.available:
        pytest.skip("Train the Autoencoder before testing CSV import")
    csv_data = (
        b"timestamp,voltage,current,power,energy\n"
        b"2026-01-01T00:00:00Z,230,2.5,575,0.0008\n"
        b"2026-01-01T00:00:00Z,230,2.5,575,0.0008\n"
        b"not-a-date,230,2.5,575,0.0008\n"
        b"2026-01-01T00:00:10Z,-2,2.5,575,0.0008\n"
    )
    with TestClient(app) as client:
        response = client.post(
            "/readings/import?source=demo",
            files={"file": ("mixed.csv", csv_data, "text/csv")},
        )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["total_rows"] == 4
    assert report["accepted_rows"] == 1
    assert report["duplicate_rows"] == 1
    assert report["rejected_rows"] == 2
    assert len(report["errors"]) == 3


def test_settings_can_update_demo_replay_interval():
    with TestClient(app) as client:
        updated = client.patch("/settings", json={"dataset_replay_interval_seconds": 15})
        assert updated.status_code == 200
        assert updated.json()["dataset_replay_interval_seconds"] == 15
        assert client.get("/settings").json()["max_csv_upload_mb"] == 10


def test_csv_power_mismatch_is_rejected():
    frame = pd.DataFrame([{
        "timestamp": "2026-01-01T00:00:00Z", "voltage": 230,
        "current": 2.5, "power": 10, "energy": 0.0008,
    }])
    with pytest.raises(ValueError, match="inconsistent"):
        clean_dataset(frame)