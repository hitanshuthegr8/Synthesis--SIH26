"""Contracts for real spatial forecast ingestion.

The repository currently contains only point forecasts. This module defines
the target grid and strict validation needed before a real gridded provider is
allowed to expose values.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GridSpec(BaseModel):
    """Target regular latitude/longitude grid for the SYNTHESIS MVP."""

    model_config = ConfigDict(frozen=True)

    south: float = 5.0
    north: float = 40.0
    west: float = 65.0
    east: float = 100.0
    resolution: float = 0.25
    latitude_count: int = 141
    longitude_count: int = 141

    @model_validator(mode="after")
    def validate_geometry(self) -> "GridSpec":
        if self.north <= self.south or self.east <= self.west:
            raise ValueError("Grid bounds must have positive extent")
        expected_latitudes = round((self.north - self.south) / self.resolution) + 1
        expected_longitudes = round((self.east - self.west) / self.resolution) + 1
        if expected_latitudes != self.latitude_count or expected_longitudes != self.longitude_count:
            raise ValueError("Grid dimensions do not match bounds and resolution")
        return self


GRID_SPEC = GridSpec()


class SpatialForecastUnavailable(Exception):
    """Raised when no real spatial forecast source is configured."""


class SpatialForecast(BaseModel):
    """Normalized values from a genuine spatial forecast source."""

    model_config = ConfigDict(protected_namespaces=())

    source: str = Field(..., min_length=1)
    variable: str = Field(..., min_length=1)
    initialization: datetime
    lead_hours: int = Field(..., ge=0, le=384)
    units: str = Field(..., min_length=1)
    grid: GridSpec
    latitudes: list[float]
    longitudes: list[float]
    values: list[list[float]]
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("latitudes", "longitudes")
    @classmethod
    def validate_axis_values(cls, values: list[float]) -> list[float]:
        if not values or any(not isfinite(value) for value in values):
            raise ValueError("Coordinate axes must contain finite values")
        if any(left >= right for left, right in zip(values, values[1:])):
            raise ValueError("Coordinate axes must be strictly increasing")
        return values

    @model_validator(mode="after")
    def validate_grid_values(self) -> "SpatialForecast":
        if len(self.latitudes) != self.grid.latitude_count:
            raise ValueError("Latitude axis length does not match GridSpec")
        if len(self.longitudes) != self.grid.longitude_count:
            raise ValueError("Longitude axis length does not match GridSpec")
        validate_axis(self.latitudes, self.grid.south, self.grid.north, self.grid.resolution, "latitude")
        validate_axis(self.longitudes, self.grid.west, self.grid.east, self.grid.resolution, "longitude")
        if len(self.values) != len(self.latitudes) or any(len(row) != len(self.longitudes) for row in self.values):
            raise ValueError("Value array shape must be latitude_count x longitude_count")
        if any(not isfinite(value) for row in self.values for value in row):
            raise ValueError("Value array cannot contain missing or non-finite values")
        return self


def validate_axis(axis: list[float], start: float, end: float, resolution: float, name: str) -> None:
    """Validate ordering, domain, spacing, and endpoint alignment."""
    tolerance = 1e-6
    if abs(axis[0] - start) > tolerance or abs(axis[-1] - end) > tolerance:
        raise ValueError(f"{name} axis does not match the configured domain")
    if any(abs((right - left) - resolution) > tolerance for left, right in zip(axis, axis[1:])):
        raise ValueError(f"{name} axis resolution must be {resolution}")


def validate_spatial_forecast(forecast: SpatialForecast) -> SpatialForecast:
    """Explicit validation entry point for provider adapters."""
    return SpatialForecast.model_validate(forecast.model_dump())


class SpatialForecastProvider(ABC):
    """Provider interface for real gridded forecast sources."""

    @abstractmethod
    def get_forecast(
        self,
        *,
        variable: str,
        lead_hours: int,
        initialization: datetime | None = None,
    ) -> SpatialForecast:
        """Return a validated spatial forecast or raise availability error."""


class UnavailableSpatialForecastProvider(SpatialForecastProvider):
    """Provider used until a repository-backed gridded source is configured."""

    def get_forecast(
        self,
        *,
        variable: str,
        lead_hours: int,
        initialization: datetime | None = None,
    ) -> SpatialForecast:
        raise SpatialForecastUnavailable(
            "Spatial forecast unavailable: no GRIB, NetCDF, raster, or other "
            "repository-backed gridded dataset is configured."
        )
