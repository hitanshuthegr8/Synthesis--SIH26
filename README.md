# SYNTHESIS
Skill-Yielding Neural-Statistical Hybrid Ensemble for Situational Integration of Forecasts

## Description
Hybrid AI-NWP Adaptive Forecast Blending System that dynamically determines which forecast source to trust based on location, lead time, season, variable, weather regime, and model disagreement.

## Architecture Overview
```text
[Ingest] -> [Regime] -> [Skill] -> [Disagreement] -> [Weights] -> [Blend] -> [Uncertainty] -> [Explain] -> [Verify]
```

## Tech Stack
- Python 3.11+
- FastAPI
- React + TypeScript
- SQLite

## Quick Start
```bash
docker compose up --build
```

## Development Setup

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

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
