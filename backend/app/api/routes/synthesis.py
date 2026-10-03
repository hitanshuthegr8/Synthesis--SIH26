"""Live multi-model AIRAVAT API: blended fields, weight maps, skill, extremes and operational runs."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.spatial import operations
from app.spatial.forecast import GRID_SPEC, SpatialForecastUnavailable
from app.spatial.products import (
    HAZARDS,
    REGIONS,
    SOURCES,
    VARIABLES,
    available_cycles,
    compute_skill,
    extremes,
    field_response,
    hazard_field,
    latest_cycle,
    layer,
    layer_units,
    point,
    skill_summary,
)

router = APIRouter(prefix="/api/synthesis", tags=["synthesis"])

LAYERS = ("blend", *SOURCES, "spread", "weights")


def _initialization(value: datetime | None) -> datetime:
    return value or latest_cycle()


def _unavailable(error: Exception, **context: object) -> dict:
    return {"status": "UNAVAILABLE", "reason": str(error), "values": None, **context}


@router.get("/catalog")
def catalog() -> dict:
    """Everything the dashboard needs to build its controls."""
    try:
        cycles = available_cycles()
    except Exception as error:  # noqa: BLE001 - catalog must still load offline
        cycles = [{"error": str(error)}]
    return {
        "sources": [{"id": source, **meta, "enabled": getattr(settings, f"{source}_ENABLED")} for source, meta in SOURCES.items()],
        "variables": [{"id": key, **value} for key, value in VARIABLES.items()],
        "layers": list(LAYERS),
        "hazards": [{"id": key, "label": value["label"], "variable": value["variable"], "units": value["units"],
                     "levels": [{"threshold": threshold, "label": label} for threshold, label in value["levels"]]}
                    for key, value in HAZARDS.items()],
        "regions": [{"id": key, "label": label} for key, label in REGIONS],
        "cycles": cycles,
        "grid": GRID_SPEC.model_dump(),
        "era5_enabled": settings.ERA5_ENABLED,
    }


@router.get("/field")
def field(
    variable: str = Query("temperature"),
    lead_hours: int = Query(24, ge=0, le=168),
    layer_name: str = Query("blend", alias="layer"),
    weighting: str = Query("adaptive", pattern="^(adaptive|equal)$"),
    source: str | None = Query(None, description="Source whose weight map to return (layer=weights)"),
    initialization: datetime | None = Query(None),
) -> dict:
    if variable not in VARIABLES:
        raise HTTPException(status_code=422, detail=f"Unsupported variable: {variable}")
    if source is not None and source not in SOURCES:
        raise HTTPException(status_code=422, detail=f"Unsupported source: {source}")
    if layer_name not in LAYERS:
        raise HTTPException(status_code=422, detail=f"Unsupported layer: {layer_name}")
    try:
        init = _initialization(initialization)
        values, provenance = layer(variable, lead_hours, init, layer_name, weighting, source)
        return field_response(values, provenance, layer_units(variable, layer_name))
    except SpatialForecastUnavailable as error:
        return _unavailable(error, variable=variable, lead_hours=lead_hours, layer=layer_name, weighting=weighting)


@router.get("/point")
def point_explanation(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=360),
    variable: str = Query("temperature"),
    lead_hours: int = Query(24, ge=0, le=168),
    initialization: datetime | None = Query(None),
) -> dict:
    if variable not in VARIABLES:
        raise HTTPException(status_code=422, detail=f"Unsupported variable: {variable}")
    try:
        return point(variable, lead_hours, _initialization(initialization), latitude, longitude)
    except SpatialForecastUnavailable as error:
        return {"status": "UNAVAILABLE", "reason": str(error), "variable": variable, "lead_hours": lead_hours}


@router.get("/skill")
def skill(
    variable: str = Query("temperature"),
    lead_hours: int = Query(24, ge=0, le=168),
    initialization: datetime | None = Query(None),
) -> dict:
    if variable not in VARIABLES:
        raise HTTPException(status_code=422, detail=f"Unsupported variable: {variable}")
    try:
        return skill_summary(compute_skill(variable, lead_hours, _initialization(initialization)))
    except SpatialForecastUnavailable as error:
        return {"status": "UNAVAILABLE", "reason": str(error), "variable": variable, "lead_hours": lead_hours}


@router.get("/extremes")
def extreme_guidance(day: int = Query(1, ge=0, le=5), initialization: datetime | None = Query(None)) -> dict:
    try:
        return {"status": "AVAILABLE", **extremes(_initialization(initialization), day)}
    except SpatialForecastUnavailable as error:
        return {"status": "UNAVAILABLE", "reason": str(error), "day": day}


@router.get("/extremes/field")
def extreme_field(hazard: str = Query("heavy_rain"), day: int = Query(1, ge=0, le=5),
                  initialization: datetime | None = Query(None)) -> dict:
    try:
        values, provenance = hazard_field(_initialization(initialization), day, hazard)
        return field_response(values, provenance, VARIABLES[HAZARDS[hazard]["variable"]]["units"])
    except SpatialForecastUnavailable as error:
        return _unavailable(error, hazard=hazard, day=day)


class RunRequest(BaseModel):
    initialization: datetime | None = None
    variables: list[str] | None = None
    leads: list[int] | None = Field(default=None)
    days: list[int] | None = None


@router.post("/runs")
def start_run(request: RunRequest) -> dict:
    try:
        run = operations.create_run(request.initialization, request.variables, request.leads, request.days)
    except (ValueError, SpatialForecastUnavailable) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    operations.start_run(run)
    return run


@router.get("/runs")
def runs() -> list[dict]:
    return operations.list_runs()


@router.get("/runs/{run_id}")
def run_status(run_id: str) -> dict:
    run = operations.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
