# Architecture

## Modular Monolith

The AIRAVAT backend is structured as a modular monolith. This allows rapid development while keeping boundaries clean for future extraction if needed.

## System Flow
Ingest → Regime → Skill → Disagreement → Weights → Blend → Uncertainty → Explain → Verify

## Modules
- `ingest`: Handles importing forecast and observation data.
- `regime`: Classifies current weather regimes.
- `skill`: Evaluates historical model performance.
- `disagreement`: Measures spread between different models.
- `weights`: Computes blending weights.
- `blend`: Applies weights to create the final forecast.
- `uncertainty`: Generates uncertainty bands.
- `explain`: Provides reasons for the chosen weights.
- `verify`: Compares past forecasts against observations.

## Data Flow Diagram
```text
Client -> API -> Blend Engine -> Weighting Logic -> Database
```

## Extension Points
For Phase 2, the system will use Python `Protocol` interfaces to swap out rule-based engines for ML-based ones seamlessly.

## Database Design (SQLite)
Tables:
- `forecast`: Stores model predictions.
- `observation`: Stores ground truth data.
- `model_skill`: Precomputed skill metrics for models.
- `blend_result`: The synthesized forecast output.
- `verification_result`: Accuracy metrics.
- `forecast_run`: Metadata for a specific forecasting session.

## API Design Overview
RESTful JSON API served by FastAPI.
