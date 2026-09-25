"""Strict deterministic verification for normalized spatial forecasts."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from math import isfinite, sqrt
from typing import Any, Protocol

from pydantic import BaseModel, Field, model_validator

from app.spatial.forecast import GRID_SPEC, GridSpec, SpatialForecast, SpatialForecastUnavailable


class SpatialTruth(BaseModel):
    """An explicitly supplied observation/truth field on a validated grid."""

    source: str = Field(..., min_length=1)
    variable: str = Field(..., min_length=1)
    initialization: datetime
    lead_hours: int = Field(..., ge=0)
    units: str = Field(..., min_length=1)
    grid: GridSpec
    latitudes: list[float]
    longitudes: list[float]
    values: list[list[float]]
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_field(self) -> "SpatialTruth":
        if len(self.latitudes) != self.grid.latitude_count or len(self.longitudes) != self.grid.longitude_count:
            raise ValueError("Truth coordinates do not match GridSpec dimensions")
        if len(self.values) != len(self.latitudes) or any(len(row) != len(self.longitudes) for row in self.values):
            raise ValueError("Truth value array shape must match coordinates")
        if any(not isfinite(value) for value in self.latitudes + self.longitudes):
            raise ValueError("Truth coordinates must be finite")
        if any(not isfinite(value) for row in self.values for value in row):
            raise ValueError("Truth values must be finite")
        return self


class SpatialVerificationResult(BaseModel):
    """Metrics and an explicit absolute-error field, not a confidence score."""

    metrics: dict[str, float | int]
    absolute_error_field: list[list[float]]
    provenance: dict[str, Any]


class TruthProvider(ABC):
    @abstractmethod
    def get_truth(self, *, variable: str, initialization: datetime, lead_hours: int) -> SpatialTruth:
        """Return explicitly sourced truth or raise availability error."""


class UnavailableTruthProvider(TruthProvider):
    def get_truth(self, *, variable: str, initialization: datetime, lead_hours: int) -> SpatialTruth:
        raise SpatialForecastUnavailable(
            "Spatial truth unavailable: no observation or truth dataset is configured."
        )


def verify_spatial_forecast(forecast: SpatialForecast, truth: SpatialTruth) -> SpatialVerificationResult:
    """Compare compatible forecast and truth fields without regridding or conversion."""
    _validate_compatibility(forecast, truth)
    metrics = compute_error_metrics(forecast.values, truth.values)
    absolute_error = [
        [abs(forecast.values[row][column] - truth.values[row][column]) for column in range(len(forecast.longitudes))]
        for row in range(len(forecast.latitudes))
    ]
    return SpatialVerificationResult(
        metrics=metrics,
        absolute_error_field=absolute_error,
        provenance={
            "verification_type": "deterministic spatial verification",
            "forecast_source": forecast.source,
            "forecast_model": forecast.provenance.get("model"),
            "forecast_initialization": forecast.initialization,
            "forecast_lead_hours": forecast.lead_hours,
            "valid_time": _valid_time(forecast.initialization, forecast.lead_hours),
            "variable": forecast.variable,
            "forecast_units": forecast.units,
            "truth_source": truth.source,
            "truth_variable": truth.variable,
            "truth_units": truth.units,
            "truth_provenance": truth.provenance,
            "grid": forecast.grid.model_dump(),
            "metrics": ["MAE", "RMSE", "Bias", "absolute error field"],
            "not_a_confidence_score": True,
        },
    )


def compute_error_metrics(
    forecast_values: list[list[float]], truth_values: list[list[float]]
) -> dict[str, float | int]:
    if (
        len(forecast_values) != len(truth_values)
        or any(not isinstance(row, list) for row in forecast_values + truth_values)
        or any(len(forecast_values[row]) != len(truth_values[row]) for row in range(len(forecast_values)))
    ):
        raise ValueError("Forecast and truth dimensions must match")
    errors = [
        forecast_values[row][column] - truth_values[row][column]
        for row in range(len(forecast_values))
        for column in range(len(forecast_values[row]))
    ]
    if not errors or any(not isfinite(value) for value in errors):
        raise ValueError("Forecast and truth values must be finite and non-empty")
    count = len(errors)
    return {
        "mae": sum(abs(error) for error in errors) / count,
        "rmse": sqrt(sum(error * error for error in errors) / count),
        "bias": sum(errors) / count,
        "valid_cell_count": count,
        "total_cell_count": count,
        "invalid_cell_count": 0,
    }


def _validate_compatibility(forecast: SpatialForecast, truth: SpatialTruth) -> None:
    if forecast.variable != truth.variable:
        raise ValueError("Forecast and truth variables must match")
    if forecast.units != truth.units:
        raise ValueError("Forecast and truth units must match; conversion is not implicit")
    if forecast.initialization != truth.initialization:
        raise ValueError("Forecast and truth initialization must match")
    if forecast.lead_hours != truth.lead_hours:
        raise ValueError("Forecast and truth lead hours must match")
    if forecast.grid != truth.grid:
        raise ValueError("Forecast and truth GridSpec must match")
    if forecast.latitudes != truth.latitudes or forecast.longitudes != truth.longitudes:
        raise ValueError("Forecast and truth coordinates must match exactly")
    declared_valid_time = truth.provenance.get("valid_time")
    if declared_valid_time is not None:
        try:
            parsed_valid_time = datetime.fromisoformat(str(declared_valid_time).replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Truth provenance valid time is invalid") from error
        if parsed_valid_time != _valid_time(forecast.initialization, forecast.lead_hours):
            raise ValueError("Forecast and truth valid UTC times must match")


def _valid_time(initialization: datetime, lead_hours: int) -> datetime:
    if initialization.tzinfo is None:
        raise ValueError("Forecast initialization must be timezone-aware")
    return initialization.astimezone(timezone.utc) + timedelta(hours=lead_hours)
