import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / "ESP32 firmware"


def test_wokwi_diagram_wires_potentiometer_to_adc_and_power():
    diagram = json.loads((FIRMWARE / "diagram.json").read_text(encoding="utf-8"))
    parts = {part["id"]: part for part in diagram["parts"]}
    assert parts["pot1"]["type"] == "wokwi-potentiometer"
    assert ["esp:34", "pot1:SIG", "green", []] in diagram["connections"]
    assert ["esp:3V3", "pot1:VCC", "red", []] in diagram["connections"]
    assert ["esp:GND.1", "pot1:GND", "black", []] in diagram["connections"]


def test_wokwi_sketch_reads_adc_and_posts_explicit_simulation_source():
    sketch = (FIRMWARE / "sketch.ino").read_text(encoding="utf-8")
    config = (FIRMWARE / "config.h").read_text(encoding="utf-8")
    wokwi_config = (FIRMWARE / "wokwi.toml").read_text(encoding="utf-8")
    entry_point = (FIRMWARE / "src" / "main.cpp").read_text(encoding="utf-8")
    diagram = json.loads((FIRMWARE / "diagram.json").read_text(encoding="utf-8"))
    parts = {part["id"]: part for part in diagram["parts"]}
    assert "analogRead(POTENTIOMETER_PIN)" in sketch
    assert 'POTENTIOMETER_PIN = 34' in sketch
    assert "API_URL" in sketch
    assert "SEND_INTERVAL_MS = WOKWI_SEND_INTERVAL_MS" in sketch
    assert "power * elapsedSeconds / 3600000.0" in sketch
    assert '\\"device_id\\":' in sketch
    assert '\\"interval_energy_kwh\\":' in sketch
    assert '\\"data_source\\":\\"wokwi_simulation\\"' in sketch
    assert "INPUT_PULLUP" in sketch
    assert "LiquidCrystal_I2C" in sketch
    assert "tone(" in sketch
    assert "WOKWI_API_HOST" in sketch
    assert "WOKWI_API_PORT" in sketch
    assert "WOKWI_API_ROUTE" in sketch
    assert "hasValidInference" in sketch
    assert "WiFi.hostByName" in sketch
    assert '#include "../sketch.ino"' in entry_point
    assert 'WOKWI_API_HOST "host.wokwi.internal"' in config
    assert "WOKWI_API_PORT 8001" in config
    assert 'WOKWI_API_ROUTE "/reading"' in config
    assert "WOKWI_SEND_INTERVAL_MS 1000UL" in config
    assert "WOKWI_HTTP_TIMEOUT_MS 2500" in config
    assert "rfc2217ServerPort = 4000" in wokwi_config
    assert "responseCode == 201" in sketch
    assert "API:CONNECTED" in sketch
    assert 'snprintf(firstLine, sizeof(firstLine), "V:%.1f I:%.2fA"' in sketch
    assert 'snprintf(secondLine, sizeof(secondLine), "P:%.0fW %s"' in sketch
    assert 'snprintf(firstLine, sizeof(firstLine), "Energy:%.3fkWh"' in sketch
    assert '"AI:ANOMALY"' in sketch
    assert 'Score:%.2e' in sketch
    assert 'writeLcdLine(0, "API:CONNECTED")' in sketch
    assert 'writeLcdLine(1, "Device:ESP32")' in sketch
    assert "Device:ESP32" in sketch
    assert "lcdScreen = (lcdScreen + 1) % 5" in sketch
    assert "http.errorToString(responseCode)" in sketch
    assert "request_id" in sketch
    assert "attempt < 2" in sketch
    assert "retrying once with request_id" in sketch
    assert "Wifi:OFFLINE" in sketch
    assert "Gateway/NET" in sketch
    assert "HTTP 422" in sketch
    assert "HTTP 500" in sketch
    assert "HTTP 201 did not contain a valid persisted inference result" in sketch
    assert '"anomaly_score"' in sketch
    assert '"threshold"' in sketch
    assert '"model_version"' in sketch
    assert 'lastDisplayedStatus = "WAITING"' in sketch
    assert 'WOKWI_DEVICE_ID "wokwi-esp32-01"' in config
    assert '\\"interval_seconds\\":' in sketch
    assert "String(elapsedSeconds, 3)" in sketch
    assert "SIMULATED INPUT" in sketch
    assert sketch.rstrip().endswith("}")
    assert parts["lcd1"]["attrs"]["pins"] == "i2c"
    assert parts["esp"]["type"] == "board-esp32-devkit-c-v4"
    assert ["esp:21", "lcd1:SDA", "green", []] in diagram["connections"]
    assert ["esp:22", "lcd1:SCL", "blue", []] in diagram["connections"]
    for pin, led, resistor, color in ((18, "ledGreen", "rGreen", "green"), (19, "ledRed", "rRed", "red")):
        assert [f"esp:{pin}", f"{led}:A", color, []] in diagram["connections"]
        assert [f"{led}:C", f"{resistor}:1", color, []] in diagram["connections"]
        assert parts[resistor]["attrs"]["value"] == "220"
        assert [f"{resistor}:2", "esp:GND.1", "black", []] in diagram["connections"]
    assert ["esp:23", "buzzer1:2", "orange", []] in diagram["connections"]
    assert ["esp:GND.1", "buzzer1:1", "black", []] in diagram["connections"]
    assert ["esp:27", "btn1:1.l", "blue", []] in diagram["connections"]
    assert ["esp:GND.1", "btn1:2.l", "black", []] in diagram["connections"]
