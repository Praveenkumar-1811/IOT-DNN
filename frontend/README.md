# Energy dashboard

This Next.js frontend reads all monitoring and analytics data from the FastAPI service. It does not synthesize readings when the API is unavailable.

From the project root in PowerShell:

```powershell
Copy-Item frontend\.env.example frontend\.env.local
npm --prefix frontend install
npm --prefix frontend run dev
```

Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to the backend origin (local default `http://127.0.0.1:8001`). Pages include the dashboard, live monitoring, anomaly history, analytics, paginated reading history with CSV export, dataset imports, model status, settings, and system health.

Run frontend checks from the project root:

```powershell
npm --prefix frontend run lint
npm --prefix frontend run build
```

See the root [README](../README.md) for backend setup, training, Wokwi connectivity, CSV provenance, and deployment guidance.
