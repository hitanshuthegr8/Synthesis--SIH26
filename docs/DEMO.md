# AIRAVAT Demo Mode

AIRAVAT Phase 1.5 runs fully offline using **DEMO MODE · SYNTHETIC BENCHMARK** adapters. Synthetic fields simulate ECMWF, GFS, GEFS, and an AI model for reproducible evaluation; they are **not** live model output.

## Quick demo

```bash
make generate-demo
make seed
docker compose up --build
```

Open the dashboard, select **Heavy Rain → Precipitation → 24h**, and click **Run Forecast Cycle**.

## Scenarios

| Scenario | Purpose |
| --- | --- |
| `normal` | Low disagreement, similar weights |
| `heavy_rain` | HEAVY_RAIN regime, high disagreement |
| `model_disagreement` | Extreme spread (alias: `model_conflict` internally) |
| `model_failure` | GFS anomaly; weight penalty and blend shift |

## Commands

| Command | Action |
| --- | --- |
| `make generate-demo` | Regenerate deterministic JSONL demo archives |
| `make seed` | Initialize SQLite from demo skill archives |
| `make reset` | Reset local demo database |
| `make test` | Run backend test suite |

## Replay

`POST /api/demo/replay` with `{ "run_id": "..." }` reproduces weights, blend, uncertainty, and explanation for the same stored run configuration.
