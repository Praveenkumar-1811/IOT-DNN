# Run EnergyGuard AI on Windows

Run commands from the workspace root: `C:\Users\prave\Desktop\IOT DNN`.

## Quick start

Run `powershell -ExecutionPolicy Bypass -File .\start-project.ps1` from the workspace root. The script starts a missing backend/frontend, reuses a healthy backend, and does not stop an existing frontend. Start Wokwi separately in VS Code.

## 1. Start the backend

Use the existing virtual environment and keep this terminal open:

```powershell
cd "C:\Users\prave\Desktop\IOT DNN"
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload
```

If PowerShell blocks activation, run the project interpreter directly:

```powershell
cd "C:\Users\prave\Desktop\IOT DNN"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload
```

## 2. Check API and model readiness

In another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8001/model/status | ConvertTo-Json
```

Health should report `status: ok`, `database: true`, and `model: true`. If the model is unavailable, verify that `backend/energy_autoencoder.keras`, `backend/scaler.pkl`, `backend/threshold.txt`, and `backend/model_metadata.json` exist. Recreate the demo model only when needed:

```powershell
.\.venv\Scripts\python.exe -m backend.train
```

API documentation: <http://127.0.0.1:8001/docs>.

`POST /reading` requires no authentication or external API key. The firmware sends this schema (values vary per sample; `request_id` is unique per reading):

```json
{
    "device_id": "wokwi-esp32-01",
    "timestamp": "2026-10-24T12:00:00Z",
    "voltage": 230.0,
    "current": 2.5,
    "power": 575.0,
    "interval_energy_kwh": 0.0001597222,
    "interval_seconds": 1.0,
    "cumulative_energy_kwh": 0.0001597222,
    "data_source": "wokwi_simulation",
    "request_id": "wokwi-esp32-01-<unique-id>"
}
```

FastAPI calculates power itself and rejects a supplied inconsistent value. The response status is **201** and the JSON includes the model `status`, `anomaly_score`, and `threshold`.

## 3. Build the ESP32 firmware

The active PlatformIO source is `ESP32 firmware/src/main.cpp`; it includes the API-connected `ESP32 firmware/sketch.ino`.

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run --project-dir "$PWD\ESP32 firmware"
```

The build artifact used by Wokwi is `ESP32 firmware/.pio/build/esp32dev/firmware.bin`. The command requires PlatformIO Core installed at the standard user path by the PlatformIO VS Code extension. If that executable is missing, install/enable the PlatformIO IDE extension and use its PlatformIO project tasks.

## 4. Start Wokwi manually

1. Open the workspace in VS Code and open `ESP32 firmware/diagram.json`.
2. The active `wokwi.toml` is in the `ESP32 firmware` subfolder. Run **Wokwi: Select Config File** and choose `ESP32 firmware/wokwi.toml`; then run **Wokwi: Start Simulator**.
3. Keep the simulator tab visible and open the serial monitor at 115200 baud. RFC2217 diagnostics are also available on `localhost:4000` after the selected config is loaded.
4. Wokwi for VS Code bundles its Private IoT Gateway, so the extension does not require the separate `wokwigw.exe` process or TCP port 9011. The firmware connects to `Wokwi-GUEST` and posts to `http://host.wokwi.internal:8001/reading` using the host/port/route constants in `ESP32 firmware/config.h`.
5. For the **browser-based Wokwi.com simulator only**, the public gateway cannot reach local services. Install/run the [standalone Wokwi IoT Gateway](https://github.com/wokwi/wokwigw/releases/latest), enable **Private Wokwi IoT Gateway** from the editor's F1 menu, and check its console for `Client connected`. Wokwi documents this as a local-network feature that may require a paid plan. Do not expose the unauthenticated API broadly through Windows Firewall.
6. After rebuilding, restart the simulation so it loads `.pio/build/esp32dev/firmware.bin`. Move the potentiometer; press MODE to cycle through potentiometer, normal-test, and anomaly-test inputs. These values are simulation proxies, not physical measurements. The trained backend model returns the final classification.

LCD/serial result guide: `AI:WAITING` means no valid inference response has arrived; `AI:OFFLINE` means Wi-Fi, DNS, transport, backend, or inference is unavailable. `API:CONNECTED` is shown only after HTTP 201 contains a persisted reading ID, model version, status, score, and threshold consistent with the returned classification. Serial reports Wi-Fi IP/gateway/DNS, API host/port/route, DNS resolution result, HTTP status, response body, and JSON validation errors. HTTP 401/403 indicates an auth layer or proxy rejected the request (the local FastAPI app itself has no auth); 404 means host/path mismatch; 422 means payload validation failed; 500/503 indicates a backend/model/storage failure. 5xx and transport failures are retried once with the same `request_id`, so a lost response does not create a duplicate row. DNS lookup failures explain that Wokwi's Public Gateway cannot reach the local computer and that the Private IoT Gateway must be enabled.

Wokwi is not launched by a terminal command in this guide. The simulator, gateway, and browser access require a manual Wokwi action.

## 5. Start the frontend

The local `frontend/.env.local` is configured for port 8001. Start the app in another terminal:

```powershell
cd "C:\Users\prave\Desktop\IOT DNN"
npm --prefix frontend run dev
```

Open <http://localhost:3000>. The frontend reads the API URL from `NEXT_PUBLIC_API_URL`; update `frontend/.env.local` and restart Next.js if the backend is elsewhere. Do not put secrets in this public variable.

## 6. Verify Wokwi delivery and persistence

Before starting the simulation, record the source count:

```powershell
$before = (Invoke-RestMethod "http://127.0.0.1:8001/readings/count?source=wokwi_simulation").count
$before
```

After Wokwi is connected and has sent samples, query the latest API reading and count:

```powershell
Invoke-RestMethod "http://127.0.0.1:8001/readings/latest?source=wokwi_simulation" | ConvertTo-Json
$after = (Invoke-RestMethod "http://127.0.0.1:8001/readings/count?source=wokwi_simulation").count
[pscustomobject]@{ Before = $before; After = $after; NewReadings = ($after - $before) }
```

Confirm `device_id` is `wokwi-esp32-01`, source is `wokwi_simulation`, and the count increased. The serial monitor must show HTTP 201 and the backend's classification response. HTTP failures or validation errors do not mean the reading was saved.

For read-only SQLite confirmation:

```powershell
@'
import sqlite3
connection = sqlite3.connect("backend/energy.db")
try:
    print(connection.execute(
        "SELECT COUNT(*), MAX(timestamp) FROM readings WHERE source = ?",
        ("wokwi_simulation",),
    ).fetchone())
finally:
    connection.close()
'@ | .\.venv\Scripts\python.exe -
```

Select `Wokwi simulation` on the dashboard and check the latest sample, timestamp, model score, and charts. The dashboard refreshes stored backend data; it does not create sensor records.

## 7. Run checks

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
npm --prefix frontend run lint
Push-Location frontend
.\node_modules\.bin\tsc.cmd --noEmit
Pop-Location
npm --prefix frontend run build
```

The backend tests use temporary databases. Do not point test runs at `backend/energy.db`.

## Troubleshooting

- **Port already in use:** choose another backend port and set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` plus `WOKWI_API_PORT` in `ESP32 firmware/config.h` to that port; restart both services and rebuild firmware.
- **CORS error:** the backend defaults to allowing `http://localhost:3000` and `http://127.0.0.1:3000`. For another frontend origin, set `CORS_ORIGINS` before starting FastAPI.
- **Wokwi host cannot resolve or connect in VS Code:** confirm the selected config is `ESP32 firmware/wokwi.toml`, keep its simulator tab visible, and inspect serial diagnostics for DNS and HTTP errors. The extension bundles its gateway; TCP port 9011 is only relevant to the standalone gateway used by browser-based Wokwi.com. `localhost` in the ESP32 URL points to the simulated ESP32, not the host.
- **HTTP 422:** inspect the serial response body. The schema requires positive voltage, non-negative finite current, and `energy` or `interval_energy_kwh`; supplied power must match voltage × current within backend tolerance.
- **Model unavailable:** inspect `/health` and `/model/status`; confirm all four model artifacts are present. Train with the virtual-environment command above only if artifacts are missing or intentionally being rebuilt.
- **Database error:** check that `backend/energy.db` is writable and that no external process has locked it. Preserve the existing database; do not delete it to troubleshoot.
- **No dashboard sample:** verify `/readings/latest?source=wokwi_simulation`, the current source selector, and that Wokwi printed HTTP 201. A healthy backend alone does not prove the device is connected.
- **Dependency errors:** activate `.venv` and install `backend/requirements.txt`; run `npm --prefix frontend install` for frontend dependencies. PlatformIO is installed separately by its VS Code extension.