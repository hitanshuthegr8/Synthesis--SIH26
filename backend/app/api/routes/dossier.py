"""Forecast dossier endpoint for an auditable run snapshot."""
from fastapi import APIRouter, HTTPException

from app.pipelines.forecast_cycle import ForecastCycleResult, cycle_registry

router = APIRouter(prefix="/api/runs", tags=["dossier"])


@router.get("/{run_id}/dossier", response_model=ForecastCycleResult)
def get_dossier(run_id: str) -> ForecastCycleResult:
    result = cycle_registry.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Forecast dossier is not available")
    return result
