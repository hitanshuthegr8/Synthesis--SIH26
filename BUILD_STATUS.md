# AIRAVAT Phase 1.5 Build Status

**Status: PHASE 1.5 COMPLETE** (backend tests green, API-driven UI, deterministic demo pipeline)

| Task ID | Description | Status | Tests | Known limitations |
| --- | --- | --- | --- | --- |
| M0-001 | Bootstrap (FastAPI + React + Docker + `/api/health`) | Complete | `test_api_health.py` | — |
| M1-006 | SQLite persistence + canonical schemas | Complete | `test_backtest_and_storage.py` | Single-node SQLite |
| M1-009 | Deterministic demo generator + MANIFEST | Complete | `test_demo_generator.py` | JSONL not Parquet |
| M2-012 | Ingestion, validation, normalization | Complete | `test_ingestion_validation.py` | — |
| M3-019 | TimeGuard + metrics + historical skill | Complete | `test_timeguard.py`, `test_leakage.py` | TimeGuard not on every repo query |
| M4-024 | Regime, disagreement, adaptive weights, explanation | Complete | `test_regime_and_disagreement.py`, `test_weighting.py` | Rule-based regimes only |
| M5-030 | Blend, uncertainty, computation trace | Complete | `test_blending_pipeline.py`, `test_phase15_pipeline.py` | Deterministic precip blend |
| M6-036 | Verification, autopsy, replay, failure injection | Complete | `test_autopsy.py`, phase15 integration | Demo scenarios only |
| M7-042 | Full Phase 1.5 API surface + dossier | Complete | `test_public_phase15_routes_*` | No auth |
| M8-050 | API-driven workstation UI (8 pages) | Complete | `test_no_hardcoded_metrics.py`, `npm run build` | MapLibre deferred; ECharts on reliability page |
| M9-061 | Property, leakage, regression, E2E tests | Complete | `test_property_invariants.py`, `test_heavy_rain_cycle_001.py`, `test_e2e_empty_database.py` | — |
| M10-071 | Submission docs + `.env.example` | Complete | Manual review | PDF dossier optional |

## Verification commands

```bash
make test          # 168+ pytest cases
make lint          # pyflakes backend
make generate-demo
make seed
docker compose up --build
```

## Killer demo checklist

1. Heavy Rain → Run Forecast Cycle → EXTREME disagreement + adaptive weights + backend blend  
2. Computation trace + Export Dossier  
3. Reliability Map + Verification + Autopsy pages  
4. Model Failure → re-run → GFS weight drop + blend change  
