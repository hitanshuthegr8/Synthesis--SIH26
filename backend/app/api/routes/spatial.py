"""Spatial forecast availability API."""

from datetime import datetime

from fastapi import APIRouter, Query

from app.core.config import settings
from app.spatial.forecast import SpatialForecastUnavailable, UnavailableSpatialForecastProvider
from app.spatial.gfs import GFSProvider
from app.spatial.ecmwf import ECMWFProvider
from app.spatial.blend_service import SpatialBlendService
from app.spatial.verification import UnavailableTruthProvider, verify_spatial_forecast
from app.spatial.era5 import ERA5Provider

router = APIRouter(prefix="/api/forecast", tags=["spatial-forecast"])


@router.get("/grid")
def get_spatial_forecast_status(
    source: str = Query("GFS"),
    model: str = Query("GFS"),
    variable: str = Query("temperature"),
    lead_hours: int = Query(24, ge=0, le=168),
    initialization: datetime | None = Query(None),
) -> dict:
    """Report spatial forecast availability without fabricating grid values."""
    if source.upper() not in {"GFS", "ECMWF"} or (
        source.upper() == "GFS" and model.upper() != "GFS"
    ) or (source.upper() == "ECMWF" and model.upper() != "IFS"):
        return {
            "status": "UNAVAILABLE",
            "source": source,
            "model": model,
            "variable": variable,
            "lead_hours": lead_hours,
            "reason": "Unsupported spatial forecast source/model.",
            "values": None,
        }
    enabled = settings.GFS_ENABLED if source.upper() == "GFS" else settings.ECMWF_ENABLED
    if source.upper() == "GFS":
        provider = GFSProvider() if enabled else UnavailableSpatialForecastProvider()
    else:
        provider = ECMWFProvider() if enabled else UnavailableSpatialForecastProvider()
    try:
        forecast = provider.get_forecast(
            variable=variable,
            lead_hours=lead_hours,
            initialization=initialization,
        )
        return {
            "status": "AVAILABLE",
            "source": forecast.source,
            "model": forecast.provenance.get("model", "GFS"),
            "variable": forecast.variable,
            "lead_hours": forecast.lead_hours,
            "initialization": forecast.initialization,
            "units": forecast.units,
            "grid_spec": forecast.grid.model_dump(),
            "latitudes": forecast.latitudes,
            "longitudes": forecast.longitudes,
            "values": forecast.values,
            "provenance": forecast.provenance,
        }
    except (SpatialForecastUnavailable, ValueError) as error:
        return {
            "status": "UNAVAILABLE",
            "source": None,
            "variable": variable,
            "lead_hours": lead_hours,
            "grid_spec": {
                "south": 5.0,
                "north": 40.0,
                "west": 65.0,
                "east": 100.0,
                "resolution": 0.25,
                "latitude_count": 141,
                "longitude_count": 141,
            },
            "reason": str(error),
            "values": None,
        }
    raise RuntimeError("Unavailable provider returned an unexpected forecast")


@router.get("/grid/blend")
def get_blended_spatial_forecast(
    variable: str = Query("temperature"),
    lead_hours: int = Query(24, ge=0, le=168),
    initialization: datetime | None = Query(None),
) -> dict:
    """Return an equal-weight blend only when both real providers succeed."""
    try:
        forecast = SpatialBlendService().get_blended_forecast(
            variable=variable,
            lead_hours=lead_hours,
            initialization=initialization,
        )
        return {
            "status": "AVAILABLE",
            "source": forecast.source,
            "model": forecast.provenance.get("model", "SYNTHESIS"),
            "variable": forecast.variable,
            "lead_hours": forecast.lead_hours,
            "initialization": forecast.initialization,
            "units": forecast.units,
            "grid_spec": forecast.grid.model_dump(),
            "latitudes": forecast.latitudes,
            "longitudes": forecast.longitudes,
            "values": forecast.values,
            "provenance": forecast.provenance,
        }
    except (SpatialForecastUnavailable, ValueError) as error:
        return {
            "status": "UNAVAILABLE",
            "source": "SYNTHESIS",
            "model": "SYNTHESIS",
            "variable": variable,
            "lead_hours": lead_hours,
            "initialization": initialization,
            "reason": str(error),
            "values": None,
        }


@router.post("/verification/spatial")
def verify_spatial_forecast_endpoint(
    source: str = Query("GFS"),
    model: str = Query("GFS"),
    variable: str = Query("temperature"),
    lead_hours: int = Query(24, ge=0, le=168),
    initialization: datetime | None = Query(None),
) -> dict:
    """Verify a real forecast against ERA5 when explicitly enabled."""
    try:
        if not settings.ERA5_ENABLED:
            raise SpatialForecastUnavailable("Spatial truth unavailable: ERA5 is disabled")
        if source.upper() == "GFS" and model.upper() == "GFS":
            forecast_provider = GFSProvider() if settings.GFS_ENABLED else UnavailableSpatialForecastProvider()
        elif source.upper() == "ECMWF" and model.upper() == "IFS":
            forecast_provider = ECMWFProvider() if settings.ECMWF_ENABLED else UnavailableSpatialForecastProvider()
        else:
            raise ValueError("Unsupported forecast source/model")
        if initialization is None:
            raise ValueError("initialization is required when ERA5 verification is enabled")
        forecast = forecast_provider.get_forecast(
            variable=variable, lead_hours=lead_hours, initialization=initialization
        )
        truth_provider = ERA5Provider() if settings.ERA5_ENABLED else UnavailableTruthProvider()
        truth = truth_provider.get_truth(
            variable=variable, initialization=initialization, lead_hours=lead_hours
        )
        result = verify_spatial_forecast(forecast, truth)
        return {"status": "AVAILABLE", **result.model_dump(mode="json")}
    except SpatialForecastUnavailable as error:
        return {
            "status": "UNAVAILABLE",
            "reason": str(error),
            "metrics": None,
            "absolute_error_field": None,
        }
    except ValueError as error:
        return {
            "status": "UNAVAILABLE",
            "reason": str(error),
            "metrics": None,
            "absolute_error_field": None,
        }
    raise RuntimeError("Unavailable truth provider returned an unexpected field")
