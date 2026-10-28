# EnergyGuard AI Project Audit

Audit date: 2026-10-24

## Scope and Preservation

- Workspace root: `C:\Users\prave\Desktop\IOT DNN`.
- There is no Git repository at the workspace root. `frontend/` is a nested Git repository with existing modified and untracked application files. Those files are treated as user work and will not be reverted.
- `backend/energy.db`, the trained model, scaler, threshold, metadata, demo CSV, `.venv/`, frontend environment files, and both firmware folders are present and must be preserved.
- No files are proposed for deletion. `wokwi-esp32/` is an incomplete PlatformIO scaffold (no firmware source or Wokwi diagram found), so its purpose is uncertain and it will be retained.

## Existing Architecture

- Backend entry point: `uvicorn backend.main:app`. FastAPI routes validate readings, score them with `AutoencoderDetector`, store results with SQLAlchemy in SQLite, expose history/analytics/model/settings endpoints, import CSVs, and optionally replay the demo CSV.
- Model artifacts in `backend/`: `energy_autoencoder.keras`, `scaler.pkl`, `threshold.txt`, and `model_metadata.json`. Expected features, in order, are voltage, current, power, and interval energy. The detector normalizes energy to the training sampling interval before inference.
- Frontend entry point: Next.js App Router in `frontend/app/`. `frontend/lib/api.ts` centralizes typed calls to the backend. Dashboard, live, anomaly, history, analytics, datasets, model, settings, and system pages use real API calls and expose loading/error/empty states. The local API URL is environment-configured; current `.env.local` and `.env.example` use port 8000.
- Main firmware project: `ESP32 firmware/`, with PlatformIO configuration, Wokwi diagram/config, and two candidate sketches: `src/main.cpp` and root `sketch.ino`.

## Findings

1. **Firmware entry-point mismatch:** `ESP32 firmware/wokwi.toml` runs `.pio/build/esp32dev/firmware.bin`, which PlatformIO builds from `ESP32 firmware/src/main.cpp`. That file only prints potentiometer-derived values and applies a local `current > 7.0` threshold. It does not contact the backend. The root `ESP32 firmware/sketch.ino` contains the intended Wi-Fi, HTTP, LCD, LED, buzzer, test-mode, and model-response integration, but PlatformIO does not currently compile it.
2. **Port mismatch with requested default:** Frontend and firmware configuration currently target port 8000. Both ports 8000 and 8001 have healthy local APIs using the same trained model. Use 8001 for the integrated local setup and update the frontend/firmware configuration together, while retaining environment-based frontend configuration.
3. **Wokwi test path mismatch:** `backend/tests/test_wokwi.py` reads files from a root `wokwi/` folder, which is absent. The actual Wokwi files are under `ESP32 firmware/`. The test suite therefore has a path/configuration mismatch that should be corrected to test the actual canonical project.
4. **Threshold margin is applied twice:** Training computes `raw_threshold * 1.35`, saves that adjusted threshold in both `threshold.txt` and metadata, and the detector multiplies the loaded value by another 1.35. Direct inspection and inference confirm the second adjustment. Remove the redundant load-time multiplier so inference uses the calibrated threshold saved by training.
5. **Model verification:** All four model artifacts are present and load successfully in the workspace virtual environment. A direct inference check classified `(230 V, 2.5 A)` as NORMAL and `(230 V, 10.5 A)` as ANOMALY. Ground-truth labels are absent; classification metrics such as precision/recall are not currently available.
6. **Runtime evidence:** Both local APIs report healthy database/model status. The model reports 51,840 training samples. Read-only checks found zero `wokwi_simulation` readings in both APIs, so end-to-end Wokwi delivery has not yet been observed.
7. **Energy/data handling:** Firmware candidate `sketch.ino` calculates interval energy as `power * elapsedSeconds / 3,600,000`, and backend schemas accept `interval_energy_kwh`, `interval_seconds`, `device_id`, and `data_source`. Backend computes power from voltage/current, normalizes interval energy only for model inference, and stores observed interval energy separately from optional cumulative energy.
8. **Frontend data:** Authored pages use the centralized API client; no production mock readings or random chart values were found in the reviewed source. Generated `.next/` bundles contain framework-generated matches and are not source files. Existing UI work must be preserved.

## Changes Applied

- Backed up the original PlatformIO `src/main.cpp`, firmware `config.h`, frontend `.env.local`, and both READMEs as `*.pre-integration-20261024.bak`. No project source, model, data, database, or environment directory was deleted.
- Changed `ESP32 firmware/src/main.cpp` to compile the existing API-enabled sketch and expose its framework headers to PlatformIO's dependency scanner.
- Updated firmware URL to `http://host.wokwi.internal:8001/reading`, made Wi-Fi retry asynchronous, bounded HTTP calls to two seconds, and only prints a stored-success message after HTTP 201 and a recognized model classification.
- Removed the redundant detector-side 1.35 threshold multiplier. Inference now uses the calibrated `threshold.txt` artifact written by training.
- Fixed Wokwi contract tests to reference `ESP32 firmware/` and match the actual diagram board/pin/wire layout. Added a saved-threshold regression check.
- Updated frontend local and example API URLs to `http://127.0.0.1:8001`, corrected README paths/ports/board/LCD supply, and added `RUN_PROJECT.md` plus `start-project.ps1`.

## Verification Results

- `python -m pytest backend\\tests -q`: **34 passed**, with five pre-existing FastAPI/Starlette/httpx deprecation warnings. Tests use temporary databases.
- Focused model tests: **8 passed**. Direct inference with the checked-in artifacts classified the existing 2.5 A fixture as NORMAL and the 10.5 A fixture as ANOMALY.
- PlatformIO build: **passed**. Firmware uses about 90.7% of configured flash.
- Frontend ESLint, local TypeScript compiler (`tsc --noEmit`), and Next.js production build: **passed**.
- Both existing APIs on ports 8000 and 8001 returned healthy status during audit. The running frontend on port 3000 returned HTTP 200 and served the configured port-8001 API URL.
- Browser verification against the running frontend selected the existing `demo` source and displayed API-backed power/current/energy metrics and recent persisted rows. This test was read-only.
- The project SQLite database has **437** Wokwi-source rows for `wokwi-esp32-01` with firmware-shaped unique request IDs, through `2026-10-27T16:57:56Z`; this is evidence of prior simulator ingestion. During the resumed check, no new row arrived in 120 seconds, and the RFC2217 port configured for serial capture did not listen, so a current live simulator connection is not yet verified.
- PowerShell syntax parsing for `start-project.ps1`: **passed**. The script was not executed because the intended backend and frontend are already running; it leaves existing listeners untouched.

## Remaining Manual Validation

Select `ESP32 firmware/wokwi.toml` with **Wokwi: Select Config File**, start/restart the VS Code Wokwi simulator, and verify serial HTTP 201, an increased `wokwi_simulation` count, the stored `device_id`, and display in the dashboard. Wokwi for VS Code bundles its Private IoT Gateway; the standalone gateway is only required by the browser simulator. `wokwi-esp32/` remains untouched as an incomplete legacy scaffold of uncertain purpose.

## API ERROR Follow-up

- `ESP32 firmware/wokwi.toml` still selects the PlatformIO binary from `.pio/build/esp32dev/`; `src/main.cpp` includes the active `sketch.ino`.
- `backend.main` exposes unauthenticated `POST /reading` with status 201. The firmware JSON matches `ReadingInput`, including power, interval energy, device ID, Wokwi source, and the new optional `request_id`. The local model and SQLite health checks are healthy; frontend CORS is unrelated to the ESP32 request.
- Port 8001 is served by a process bound to `0.0.0.0`; its health and model-status endpoints are healthy. The VS Code extension's installed version bundles the Private IoT Gateway, while the project's `wokwi.toml` resides below the workspace root and may need to be explicitly selected through **Wokwi: Select Config File**. The standalone gateway's TCP 9011 listener is not a valid connection check for the VS Code extension.
- Windows Firewall is enabled; the active Wi-Fi connection is classified Public, no explicit TCP/8001 inbound allow rule was found, and default inbound action is not explicitly Allow. No broad firewall exception was created because this API has no authentication. If Private Gateway connections are still blocked after enabling the gateway, add only a narrowly scoped rule appropriate to the gateway and network; do not expose the API to all public networks.
- An isolated real-HTTP test against port 8002 with a temporary DB returned **201 twice** for the same `request_id`; both responses returned reading ID 2 and the temporary source count stayed 1. Server log: `POST /reading HTTP/1.1 201 Created` twice, then `GET /readings/count?source=wokwi_simulation HTTP/1.1 200 OK`. The test server was stopped; the project database was not used.
- The exact status behind the user's previously displayed generic `API ERROR` cannot be recovered because the original Wokwi serial response/status was not available. In the prior firmware, that label conflated positive non-201 HTTP responses with malformed 201 response bodies. The new firmware prints the HTTP status/body and distinguishes transport, Wi-Fi, HTTP, and malformed-response states. After rebuilding, restarting Wokwi and inspecting Serial will identify any remaining status-specific problem.
- The final ESP32 firmware rotates five 16x2 LCD screens every 2.5 seconds: sensor voltage/current and power/status, interval energy/AI status, AI/status with the backend anomaly score, API connected/device, or API error with HTTP status. `AI:WAITING` and `AI:OFFLINE` are shown until a valid backend classification is received. Serial logs every response body, including the first transient failure before retry.
- An optional `request_id` is persisted with a partial unique index for non-null values. Firmware creates one ID per sample and retries transport/3xx/5xx failures at most once with that same ID. A repeated POST returns the original stored row; the real-HTTP verification confirmed both POSTs returned 201 with reading ID 2 and a temporary database count of 1.
- Frontend API fallback and local configuration both target `127.0.0.1:8001`; the backend CORS defaults already permit the actual frontend origins (`localhost:3000` and `127.0.0.1:3000`). Frontend reading types include optional `request_id`.
- C/C++ IntelliSense now explicitly resolves ESP32 Wi-Fi/HTTP/Wire headers. PlatformIO build and C++ diagnostics both pass.