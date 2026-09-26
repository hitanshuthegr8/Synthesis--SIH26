"""Forecast autopsy retrieval API."""
from fastapi import APIRouter, HTTPException

from app.domain.verification import ForecastAutopsy
from app.pipelines.forecast_cycle import cycle_registry

router = APIRouter(prefix="/api/autopsy", tags=["autopsy"])


@router.get("/{run_id}", response_model=ForecastAutopsy)
def get_autopsy(run_id: str) -> ForecastAutopsy:
    result = cycle_registry.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "RUN_NOT_FOUND", "message": "Forecast autopsy is not available", "run_id": run_id, "recoverable": False}})
    return result.autopsy
