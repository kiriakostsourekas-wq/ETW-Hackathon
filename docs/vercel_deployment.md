# Vercel Deployment

The Vercel deployment target is the React dashboard in `frontend/`.

## What Deploys

- Vercel builds `frontend/` with Vite.
- Static output is served from `frontend/dist`.
- `/api/dashboard` is rewritten to `frontend/public/demo-dashboard.json` for a working static hackathon demo.
- The Python optimizer API remains the live/local backend. For a hosted live API, set `VITE_API_BASE` to that backend URL in Vercel environment variables.

## Why The Static Fallback Exists

The Python pipeline downloads HEnEx, IPTO, and Open-Meteo files, trains/selects a forecast model, solves the MILP, and emits a large dashboard payload. That is useful locally and for model development, but it is not a good first Vercel step because it can take tens of seconds on cold public-data fetches.

The committed `demo-dashboard.json` keeps the dashboard functional on every Vercel preview while preserving the live API path for development.

## Deploy From GitHub

1. Import `https://github.com/kiriakostsourekas-wq/ETW-Hackathon` into Vercel.
2. Keep the project root as the repository root.
3. Vercel will read `vercel.json`:
   - install: `cd frontend && npm ci`
   - build: `cd frontend && npm run build`
   - output: `frontend/dist`
4. Optional: set `VITE_API_BASE` if the Python API is hosted somewhere reachable from the browser.

## Local Verification

```bash
cd frontend
npm install
npm run build
npm run preview
```

For live local API verification:

```bash
PYTHONPATH=src python3 -m batteryhack.api_server --port 8000
cd frontend
VITE_API_BASE=http://127.0.0.1:8000 npm run dev
```

If the API is down, the frontend falls back to `/demo-dashboard.json`.
