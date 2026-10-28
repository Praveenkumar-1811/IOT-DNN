# IoT-Based Building Energy Anomaly Detection

A local, end-to-end demonstration that sends ESP32/Wokwi electrical readings to FastAPI, scores each observation with a trained Keras autoencoder, stores results in SQLite, and displays readings and anomalies in a Next.js dashboard.

The generated training CSV is **synthetic demo-normal data**, not a public dataset or campus measurement. No campus data was supplied with this project. The public-data adapter supports a selected electricity meter from Building Data Genome Project 2 (BDG2); its source and any derived values are recorded separately from live ESP32 readings.

## What Runs

```text
Wokwi ESP32 + potentiometer
        | JSON every ~1 s (simulated readings)
        v
FastAPI validation -> calibrated Keras autoencoder -> SQLite
        ^                                         |
        | CSV import (campus/public/demo)          | REST polling
                                                  v
                                      Next.js dashboard and analytics
```

## Project Layout

```text
backend/                 FastAPI, SQLAlchemy/SQLite, data cleaning, AE train/inference
  models.py               SQLAlchemy reading, import, settings, and model-metadata tables
  data/                  Generated demo data and local imported CSVs
  experiments/           Optional MOMENT comparison runner
  tests/                 API, provenance, and dataset adapter tests
frontend/                Next.js App Router, TypeScript, Tailwind, Recharts
ESP32 firmware/          PlatformIO project, Wokwi diagram, firmware, and configuration
wokwi-esp32/             Retained legacy PlatformIO scaffold; not the active Wokwi project
README.md                Setup and research notes
.env.example             Local environment examples
render.yaml              Render API service template
PROJECT_AUDIT.md         Verified architecture and integration findings
RUN_PROJECT.md           Windows PowerShell startup and verification guide
```

## Prerequisites

- Windows 10/11 and Python 3.11
- Node.js 20.9 or newer and npm
- Internet for the initial Python/npm installs and (optionally) public datasets/MOMENT weights
- Wokwi browser simulation or the Wokwi VS Code extension for the ESP32 demonstration

TensorFlow is installed in the backend virtual environment. Its Windows CPU build is sufficient for the included small model. A GPU is not required for the default autoencoder.

## Local Setup

Run these commands from the workspace root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
npm --prefix frontend install
Copy-Item frontend\.env.example frontend\.env.local
```

If PowerShell blocks `Activate.ps1`, you can avoid changing the execution policy and call the virtual-environment interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m backend.generate_demo_data
.\.venv\Scripts\python.exe -m backend.train
```

`frontend/.env.local` uses `NEXT_PUBLIC_API_URL=http://127.0.0.1:8001`. Set this variable to the deployed backend URL when deploying the frontend. Backend settings are process environment variables; see `.env.example`.

## Train and Run

Generate the clearly labeled demo-normal dataset and train once:

```powershell
python -m backend.generate_demo_data
python -m backend.train
```

Training saves `backend/energy_autoencoder.keras`, `backend/scaler.pkl`, `backend/threshold.txt`, and `backend/model_metadata.json`. The model is not retrained at API startup. Training is chronological: the first 60% fits the scaler/model, the next 20% calibrates the percentile threshold, and the final 20% remains held out for comparison. If the CSV has an `anomaly`, `label`, `is_anomaly`, `ground_truth`, or `is_anomalous` column, labeled anomalous rows are excluded from autoencoder fitting.

Start the backend in one terminal from the workspace root:

```powershell
uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload
```

Start the frontend in another terminal:

```powershell
npm --prefix frontend run dev
```

Open <http://localhost:3000>. API documentation is at <http://localhost:8001/docs>. The backend replays one row from `backend/data/demo_energy_data.csv` immediately and at the configured interval, scoring and storing each new reading under the separate `demo` source. The replay gives each inserted row a current timestamp and preserves the dataset's original energy feature so it remains consistent with model training; use Settings to stop or restart it. `DATASET_REPLAY_PATH` and `DATASET_REPLAY_INTERVAL_SECONDS` can override the file and default interval. The dashboard defaults to the distinct `wokwi_simulation` source, polls stored Wokwi readings every second, and refreshes aggregate analytics every ten seconds. Dashboard polling fetches data only; it never creates records. Demo, public-dataset, authorized campus, and other live-sensor sources remain separately selectable. When the API is unavailable, the UI reports that state instead of substituting readings.

Run tests and frontend checks:

```powershell
python -m pytest backend\tests -q
npm --prefix frontend run lint
npm --prefix frontend run build
```

## Wokwi ESP32 Simulation

### Wiring table

The diagram uses Wokwi's ESP32 DevKit C V4 board model.

| Component | Wokwi pin | ESP32 pin | Notes |
|---|---|---|---|
| Potentiometer | SIG | GPIO34 | ADC input; simulated current only |
| Potentiometer | VCC / GND | 3V3 / GND | Use 3.3 V, never 5 V on GPIO34 |
| LCD1602 I2C | SDA / SCL | GPIO21 / GPIO22 | I2C address `0x27` |
| LCD1602 I2C | VCC / GND | 5V / GND | I2C module power |
| Green LED | Anode through 220 Ω; cathode | GPIO18 / GND | Lit only when API reports NORMAL |
| Red LED | Anode through 220 Ω; cathode | GPIO19 / GND | Lit only when API reports ANOMALY |
| Piezo buzzer | + / − | GPIO23 / GND | Three short beeps on transition to ANOMALY |
| Pushbutton | Contact / other contact | GPIO27 / GND | `INPUT_PULLUP`; cycles pot, test-normal, test-anomaly |

### Start and connect

1. Start the backend from the project root: `uvicorn backend.main:app --host 0.0.0.0 --port 8001`. Check `http://127.0.0.1:8001/health` and `http://127.0.0.1:8001/docs`.
2. In another terminal, start the frontend: `npm --prefix frontend run dev`, then open `http://localhost:3000`.
3. This workspace keeps `wokwi.toml` under `ESP32 firmware/`, not at the workspace root. In VS Code, run **Wokwi: Select Config File** and select `ESP32 firmware/wokwi.toml`, then run **Wokwi: Start Simulator**. Open the simulator tab and serial monitor at 115200 baud. The config enables RFC2217 serial forwarding on `localhost:4000`; keep the simulator tab visible while collecting output.
4. PlatformIO builds `ESP32 firmware/src/main.cpp`, which includes the API-connected `ESP32 firmware/sketch.ino`. Firmware targets `host.wokwi.internal:8001/reading` (configured as host, port, and route in `ESP32 firmware/config.h`) and posts simulated readings once per second. It sends `device_id`, `data_source: "wokwi_simulation"`, and a unique `request_id`. HTTP 201 plus a valid model result confirms acceptance and persistence.
5. Wokwi for VS Code bundles its Private IoT Gateway; no separate `wokwigw.exe` or TCP 9011 listener is needed for this extension. For the **browser-based Wokwi.com simulator**, the public gateway cannot reach services on your computer: run the standalone Wokwi IoT Gateway, enable **Private Wokwi IoT Gateway** in the Wokwi editor's F1 menu, and use `host.wokwi.internal`. Wokwi documents this browser Private Gateway as a local-network feature that may require a paid plan. Do not substitute `localhost` in the ESP32 URL; that would refer to the simulated device.
6. If running a different local simulator/container, set `WOKWI_API_HOST`, `WOKWI_API_PORT`, and `WOKWI_API_ROUTE` in `ESP32 firmware/config.h` to the address reachable from that simulator.
7. On the simulation, turn the potentiometer to vary the simulated current. Press MODE to cycle between the potentiometer, a fixed 2.5 A normal demonstration, and a fixed 10.5 A anomaly demonstration. The Autoencoder remains authoritative; a test-mode input is not guaranteed to be classified anomalous by every trained model.

Every firmware value is explicitly simulated, not a physical electrical measurement. Power is voltage × simulated current. Interval energy is `power_W × elapsed_seconds / 3,600,000` kWh; the API also accepts the prior `energy` field for backward compatibility and stores both response names with the same interval value. The backend validates the reading and power, normalizes energy to the model's training cadence only for inference, and persists the observed interval energy and model result. The LCD displays voltage/current and power/status; the green/red LED state follows the latest successful API classification. The buzzer emits a short three-chirp pattern only when the reported status transitions into ANOMALY; it does not sound continuously. If the API is unreachable, the LCD displays an offline/error state and both status LEDs turn off.

**Safety:** This is a software simulation. Never connect mains voltage to the ESP32, potentiometer, breadboard, LEDs, or LCD. Use only the simulator and low-voltage development-board wiring.

### Troubleshooting

- **HTTP transport error / no dashboard samples:** confirm `/health` is healthy and FastAPI is bound to `0.0.0.0:8001`. In VS Code, select `ESP32 firmware/wokwi.toml` with **Wokwi: Select Config File**, restart the simulator, and inspect its serial output (also forwarded to `localhost:4000`). The VS Code extension bundles the gateway. Only browser-based Wokwi.com requires the standalone gateway and its Private Gateway toggle.
- **HTTP 422:** inspect the Serial Monitor response body; check the configured URL, valid timestamp, positive voltage, finite non-negative current/energy, and consistency of reported power with voltage × current.
- **LCD stays blank:** check I2C SDA=21/SCL=22, 3V3/GND, `0x27`, and the `LiquidCrystal I2C` library listed in `ESP32 firmware/libraries.txt`.
- **LED/buzzer does not indicate a result:** indicators change only after a valid classified API response; check GPIO18/19/23 wiring and the API response in Serial Monitor.
- **Timestamps appear incorrect:** allow NTP to synchronize over Wokwi Wi-Fi and look for the unsynchronized-clock note in Serial Monitor.

Check `GET http://127.0.0.1:8001/health` on the host before starting the simulation. The current is a potentiometer-derived demonstration proxy, not a calibrated current transformer.

Dataset imports are recorded in `GET /datasets` with accepted/rejected/duplicate counts and row-level errors. Reading history supports offset pagination with `GET /readings?limit=25&offset=0`; the frontend history page includes source/status/date filters and exports the displayed page. `GET /settings` reports safe runtime configuration, and `PATCH /settings` accepts a `dataset_replay_interval_seconds` value from 1 to 3600. Dataset uploads are limited to 10 MB and never replace model artifacts or existing readings.

Power is calculated by the backend from `voltage × current`; a supplied power value that differs by more than the validation tolerance is rejected. Energy is kWh used during that one sampling interval, not a lifetime meter counter. The simulator's current is a demonstration proxy, not a calibrated physical current transformer.

## Data Sources and Campus Measurements

Every database row has a `source`: `wokwi_simulation`, `live`, `campus`, `public_dataset`, or `demo`. Wokwi posts are stored with a device ID and their explicit simulation provenance; dataset replay rows are tagged `demo`. The dashboard, anomaly view, history, and analytics views select/filter these sources separately. CSV imports only allow `campus`, `public_dataset`, or `demo`, so Wokwi data cannot be mislabeled as campus measurements.

CSV import expects `timestamp`, `voltage`, `current`, `power`, and `energy`. Column aliases such as `datetime`, `amps`, `volts`, and `watts` are supported. Missing power is calculated from voltage and current; missing energy defaults to a five-second interval estimate. Invalid timestamps, non-finite/negative physical values, impossible ranges, duplicates, and inconsistent reported power are handled during preprocessing.

**Campus data is not included.** To use authorized campus meter exports, map their timestamp, voltage, current, power, and interval-energy columns to the format above and upload them in Settings as `Campus data`. If the campus provides only an electricity meter reading, do not claim its voltage/current are measured. Ensure permission and remove building/person identifiers before importing. Readings remain tagged `campus` and separate from Wokwi.

### Public Building-Energy Dataset

The included adapter targets the public [Building Data Genome Project 2 (BDG2)](https://github.com/buds-lab/building-data-genome-project-2). Its maintainers describe 3,053 meters across 1,636 non-residential buildings at hourly frequency during 2016–2017. It contains electricity and other meter types; it is not campus data and generally does not contain this project's voltage/current channels.

Download a BDG2 meter CSV from the official repository/release and select one electricity meter column (wide files) or building ID (long files). Exact column names vary by chosen file:

```powershell
python -m backend.prepare_bdg2 path\to\bdg2-meter-file.csv backend\data\bdg2-building.csv --meter-column "EXACT_ELECTRICITY_METER_COLUMN"
```

For long-format files, use `--building-id ID --meter-type electricity`. The adapter maps each hourly kWh reading to hourly-average power and derives current from the explicit nominal-voltage assumption (230 V by default). A sidecar `.metadata.json` records the dataset, selected series, interval, and the fact that voltage/current are **derived, not measured**. Import the normalized file in Settings as `Public dataset`; it will be stored under that source, separate from live readings.

Published reference: Miller et al., “The Building Data Genome Project 2, energy meter data from the ASHRAE Great Energy Predictor III competition,” *Scientific Data* 7, 368 (2020), [doi:10.1038/s41597-020-00712-x](https://doi.org/10.1038/s41597-020-00712-x).

To train an autoencoder on a prepared public or campus file instead of the demo file, set the environment variable before training:

```powershell
$env:TRAINING_DATA = "backend\data\bdg2-building.csv"
python -m backend.train
```

The imported CSV's features and the training CSV must use the same physical units and sampling interval for meaningful results. Public hourly data and five-second Wokwi data are different domains; train and compare within a selected source rather than claiming direct cross-domain performance.

## API

- `GET /` API identity and docs link
- `GET /health` API, database, and model availability
- `POST /reading` score and persist one live reading (`source` query parameter can explicitly select a source)
- `GET /readings?limit=100&offset=0&source=live` paginated recent readings
- `GET /readings/count?source=live` filtered reading count
- `GET /readings/latest?source=live` latest reading for a source
- `GET /anomalies?days=7&source=live` anomaly history
- `GET /analytics?source=live` totals and daily/weekly/monthly summaries
- `GET /model/status` model, learned threshold, and training metadata
- `POST /readings/import?source=campus` multipart CSV import
- `GET /datasets` import provenance, row counts, and validation errors
- `GET /settings` safe runtime settings; `PATCH /settings` changes demo replay interval

`POST /reading` expects finite voltage/current/energy values; `power` is optional but checked if provided. Anomaly score is mean squared error between the same four StandardScaler-normalized features used in training and their Keras reconstruction. The threshold is learned from the configured percentile of held-out normal calibration errors. Every stored reading includes the model version, score, and threshold used. Severity is relative to that learned threshold and does not diagnose a fault. CSV import stores each accepted reading and its dataset-import reference in one database transaction; the import response and `GET /datasets` include accepted, rejected, duplicate, and row-error details.

## Model Evaluation and MOMENT Baseline

No ground-truth anomaly labels are included in the demo CSV or BDG2 adapter output, so precision, recall, F1, accuracy, and confusion matrices are **not available** for those data. The system does not invent them. Add a supported label column to a separately prepared labeled file when truth is known.

The optional experiment compares the saved autoencoder with zero-shot MOMENT reconstruction on a common chronological 20% test partition. Install the additional dependencies and download the official small checkpoint on first use:

```powershell
pip install -r backend\experiments\requirements-moment.txt
python -m backend.experiments.moment_comparison backend\data\YOUR_TRAINING_FILE.csv --checkpoint AutonLab/MOMENT-1-small
```

Set `TRAINING_DATA` to that same file and train the autoencoder first. The experiment calibrates each threshold without looking at test labels, reports inference time/error distributions, and only reports supervised classification metrics when labels are present. Results are written to `backend/experiments/results/moment_comparison.json`. MOMENT is not required by the API; no MOMENT result is included or claimed until this experiment has actually run in the target environment.

The runner follows the [official MOMENT reconstruction tutorial](https://github.com/moment-timeseries-foundation-model/moment/blob/main/tutorials/anomaly_detection.ipynb) and the [MOMENT package/model instructions](https://github.com/moment-timeseries-foundation-model/moment). Large checkpoints need substantial RAM/GPU resources; use the small checkpoint first.

## Deployment

### Render API

`render.yaml` provides a starting service definition. In Render, deploy from the repository root, set `CORS_ORIGINS` to the exact deployed Vercel origin(s), and review the build/start commands. The build trains the configured demo model; use an authorized, persistent training dataset if deploying research results. Render's local filesystem can be ephemeral depending on the plan, so SQLite history may disappear on restart/redeploy. Use a persistent disk or migrate the database layer to managed PostgreSQL for durable hosted data.

### Vercel Frontend

Import this repository in Vercel, set the root directory to `frontend`, and configure `NEXT_PUBLIC_API_URL` as the deployed Render service URL. Redeploy after changing this public build-time variable. Add the Vercel origin to the backend's `CORS_ORIGINS`.

## Limitations

- Sensor hardware is simulated; no real electrical isolation, calibration, or safety protection is implemented.
- Demo training data is generated synthetic normal load with no fault labels.
- Campus readings were not provided; the `campus` path is an import capability, not a claim of campus access.
- BDG2 electricity energy is hourly; the voltage/current conversion uses an explicit fixed nominal-voltage assumption.
- The model detects deviations from learned feature distributions, not a named equipment fault.
- SQLite is a local starting point; concurrent production ingestion and durable cloud history need managed storage.
- The optional MOMENT run downloads third-party weights and may need substantial compute. No comparison result is fabricated.