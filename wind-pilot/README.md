# Day-ahead wind forecast desk

Web app for a UK energy utility's day-ahead buying team. For every January 2026 delivery day it shows
(1) the latest national wind forecast available when the purchase decision had to be made, and
(2) how accurate such forecasts have been, so the team can size a buffer.
Data: Elexon BMRS only: `FUELHH` (actual WIND) and `WINDFOR` (forecasts).

**AI use:** this project was built with assistance from Claude (Anthropic). I reviewed and own the code.

## Key assumptions (change in one place)
- **Decision time:** forecasts published up to **09:00 UK time on D-1** are usable. Configurable in the UI
  (`DEFAULT_CUTOFF` in `backend/app/analysis.py`). Real GB day-ahead auctions close in the morning of D-1; check the exact gate time for your venue.
- For each target half-hour we use the forecast with the latest `publishTime <= cutoff`.
- `error = forecast - actual`. Positive = wind over-forecast = shortfall risk.
- "Shortfall buffer" = P90 of the error (floored at 0): wind came in below forecast by more than this in only 10% of half-hours.
- nMAE (MAE / mean actual) is used instead of MAPE, which explodes when output is near zero.

## Files
| Path | Purpose |
|---|---|
| `backend/app/analysis.py` | Forecast selection, join with actuals, metrics (pure pandas, unit tested) |
| `backend/app/main.py` | FastAPI: `/api/meta`, `/api/day`, `/api/summary`; also serves the built UI |
| `backend/ingest.py` | Pulls Elexon data into `data/*.csv.gz` (`--demo` makes synthetic data) |
| `backend/tests/` | pytest: selection logic, cutoff, metrics, API |
| `frontend/src/App.jsx` | React UI (Recharts) |
| `data/` | Stored extracts so the app does not depend on Elexon at runtime |
| `Dockerfile` | Multi-stage: build UI, then Python image serving API + UI |

## Run it
**1. Load real data (required before deploying; the repo ships synthetic demo data so it starts offline):**
```
pip install -r backend/requirements.txt
python backend/ingest.py          # real Elexon data; writes data/
```
**2a. Docker:** `docker compose up --build` then open http://localhost:8000

**2b. Local dev:**
```
uvicorn app.main:app --app-dir backend --reload          # API on :8000
cd frontend && npm install && npm run dev                # UI on :5173
```
**Tests:** `cd backend && python -m pytest`

## Deployed app
<add Render / Heroku / Fly URL here>

## Known limitations / next steps
- Single cutoff time for all days; no per-venue gate closures.
- Static data extract; a scheduled refresh job would be needed for production.
- National level only, per scope.
