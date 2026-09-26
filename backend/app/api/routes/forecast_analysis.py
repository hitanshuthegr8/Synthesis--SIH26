"""Forecast-analysis endpoints backed by the complete cycle pipeline."""
from fastapi import APIRouter, HTTPException

from app.api.routes.pipeline import PipelineRunRequest
from app.domain.uncertainty import BlendResult
from app.pipelines.forecast_cycle import NoUsableSourcesError, cycle_registry, run_forecast_cycle

router = APIRouter(prefix="/api/forecast", tags=["forecast-analysis"])


@router.post("/analyze", response_model=BlendResult)
def analyze_forecast(request: PipelineRunRequest) -> BlendResult:
    """Execute a full cycle and return its concise forecast output."""
    try:
        return run_forecast_cycle(
            request.scenario,
            request.lead_hours,
            unavailable_sources=tuple(request.unavailable_sources),
            corrupt_sources=tuple(request.corrupt_sources),
        ).blend
    except NoUsableSourcesError as error:
        raise HTTPException(status_code=503, detail={"error": {"code": "NO_USABLE_SOURCES", "message": str(error), "recoverable": True}}) from error


@router.get("/{run_id}", response_model=BlendResult)
def get_forecast(run_id: str) -> BlendResult:
    result = cycle_registry.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Forecast run is not available")
    return result.blend
