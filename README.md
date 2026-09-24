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

## Phase 1 Features
- Rule-based weighting
- Weather regime classification
- Skill evaluation
- Interactive UI dashboard
- Verification metrics
- Clearly labelled offline demo scenarios: Normal, Heavy Rain, and Model Conflict

## Disclaimer
This project is an early-stage prototype (Phase 1). Results are illustrative and not validated for operational forecasting. Future phases (Phase 2) will integrate robust Machine Learning weighting algorithms.

## License
MIT
