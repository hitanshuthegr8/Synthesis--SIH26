# AIRAVAT
Hybrid AI–NWP multi-model forecast blending for India (SIH 2026 · MoES / NCMRWF, Disaster Management).

## What it does
AIRAVAT pulls three live forecast sources, learns where each one is reliable, and issues one adaptive blend plus extreme-weather guidance:

| Source | Type | Data |
|---|---|---|
| NOAA GFS | Physics NWP | NOMADS 0.25° filter service |
| ECMWF IFS | Physics NWP | ECMWF open data, byte-range GRIB2 |
| ECMWF AIFS | AI / ML model | ECMWF open data (`aifs-single`) |

Variables: 2 m temperature, afternoon maximum temperature, 24 h rainfall and 10 m wind speed, on a fixed 0.25° India grid (5–40°N, 65–100°E).

| Problem-statement outcome | Where it lives |
|---|---|
| Dynamically blended forecast | **Blend explorer**: per-cell bias correction plus skill weights, with a 3D map and a per-cell breakdown |
| Model weight maps | **Weight maps & skill**: weight map per model, regional table, and weights by lead time |
| Improved forecast skill | Leave-one-out error of AIRAVAT vs equal weights and each model, against three references |
| Extreme-weather guidance | **Extreme weather**: IMD rainfall categories, heat and wind thresholds, model agreement, single-model watch signals |
| Operational workflow | **Operations** page and `scripts/run_operational_blend.py` for cron or Task Scheduler |

The **Blending lab** shows the regime- and disagreement-aware point engine on clearly labelled synthetic scenarios.

### How the weights are learned
1. For recent cycles, each model's forecast is compared with the mean of the GFS and IFS 00 UTC analyses at the valid time.
2. Per-cell mean error (bias) and mean absolute error are smoothed over ±1°.
3. Bias is subtracted, and weights are set in proportion to 1 / MAE. Both are shrunk toward the prior (zero bias, equal weights) while history is short.
4. Skill is reported leave-one-out: each day is scored with weights learned from the other days only.

Honest limits:
- Model analyses favour the model that made them. So blend-versus-single-model gains are indicative. Adaptive-versus-equal is the like-for-like comparison.
- Independent verification needs ERA5: set `ERA5_ENABLED=true` and `ERA5_CDS_KEY` in `backend/.env`.
- Rainfall and max temperature have no analysis reference, so they use equal weights until an observed reference is added.
- ECMWF open data keeps about four days. GRIB files are cached under `backend/data/`, so history grows as the workflow runs daily.

## Run locally

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```
Create `backend/.env`:
```
GFS_ENABLED=true
ECMWF_ENABLED=true
AIFS_ENABLED=true
```
Start it (use another port if 8000 is taken):
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Skip `--reload` on Windows: its worker can hang during GRIB decoding.

### Frontend
```bash
cd frontend
npm install
set VITE_API_BASE_URL=http://127.0.0.1:8000   # PowerShell: $env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```
Open http://localhost:5173.

The first request for a new cycle downloads and decodes GRIB from three centres and scores past cycles, which takes about a minute. After that, responses come from the cache. Run the operational workflow once after startup to warm everything up.

### Operational run (daily, after ~08:00 UTC)
```bash
backend\venv\Scripts\python scripts\run_operational_blend.py --variables temperature precipitation wind_speed --leads 24 48 72 --days 0 1 2
```

### Tests
```bash
cd backend
python -m pytest -q
```
The suite is offline: a fixture disables the live providers even when `.env` enables them.

## Docker
```bash
docker compose up --build
```

## Tech stack
Python 3.11+, FastAPI, xarray/cfgrib/ecCodes, NumPy/SciPy · React + TypeScript + Vite, three.js

## Phase 1.5 (submission scope)

End-to-end adaptive forecast fusion: ingestion → validation → skill → regime → disagreement → weights → blend → uncertainty → explanation → verification → autopsy.

**DEMO MODE · SYNTHETIC BENCHMARK** — all four sources are deterministic adapters; computation is real.

```bash
make setup
make generate-demo
make seed
make test
docker compose up --build
```

See [docs/DEMO.md](docs/DEMO.md), [docs/ALGORITHM.md](docs/ALGORITHM.md), and [BUILD_STATUS.md](BUILD_STATUS.md).

## Disclaimer

Forecast guidance only. Not an official warning service. Demo results are not operational verification. Phase 2 adds research-grade probabilistic blending and live adapters.

## License
MIT
