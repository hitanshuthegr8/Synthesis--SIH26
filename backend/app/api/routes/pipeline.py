"""Forecast-cycle and computation trace API."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.pipelines.forecast_cycle import (
    ComputationTrace,
    ForecastCycleResult,
    NoUsableSourcesError,
    cycle_registry,
    run_forecast_cycle,
)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

ScenarioName = Literal["normal", "heavy_rain", "model_conflict", "model_disagreement", "model_failure"]
SourceName = Literal["ecmwf", "gfs", "gefs", "ai"]


class PipelineRunRequest(BaseModel):
    scenario: ScenarioName = "heavy_rain"
    lead_hours: int = Field(default=24, ge=0, le=168)
    unavailable_sources: list[SourceName] = Field(default_factory=list)
    corrupt_sources: list[SourceName] = Field(default_factory=list)


@router.post("/run", response_model=ForecastCycleResult)
def run_pipeline(request: PipelineRunRequest) -> ForecastCycleResult:
    try:
        return run_forecast_cycle(
            request.scenario,
            request.lead_hours,
            unavailable_sources=tuple(request.unavailable_sources),
            corrupt_sources=tuple(request.corrupt_sources),
        )
    except NoUsableSourcesError as error:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "NO_USABLE_SOURCES", "message": str(error), "recoverable": True}},
        ) from error


@router.get("/{run_id}", response_model=ForecastCycleResult)
def get_pipeline(run_id: str) -> ForecastCycleResult:
    result = cycle_registry.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "RUN_NOT_FOUND", "message": "Forecast run is not available", "run_id": run_id, "recoverable": False}})
    return result


@router.get("/computation/{run_id}", response_model=ComputationTrace)
def get_computation(run_id: str) -> ComputationTrace:
    result = cycle_registry.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "RUN_NOT_FOUND", "message": "Computation trace is not available", "run_id": run_id, "recoverable": False}})
    return result.trace
