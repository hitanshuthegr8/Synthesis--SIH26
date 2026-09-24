"""Domain model for weather forecasts.

Purpose:
    Represents a single forecast value from a specific model for a specific
    variable, location, initialization time, and lead time.

Inputs:
    Raw forecast data from any source (ECMWF, GFS, AI, GEFS, etc.)

Outputs:
    Validated, normalized Forecast objects with consistent types.

Algorithm:
    Pydantic validation with custom validators for physical constraints.

Failure cases:
    - Invalid latitude/longitude raises ValidationError
    - Negative lead_hours raises ValidationError
    - Unsupported variable raises ValidationError
    - Missing required fields raise ValidationError

Future replacement:
    None — this is a stable domain primitive.
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import SUPPORTED_VARIABLES, VARIABLE_UNITS


class Forecast(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """A single forecast value from one model.

    Represents the normalized internal format that all forecast sources
    must be converted to before entering the blending engine.
    """

    model_id: str = Field(..., min_length=1, description="Source model identifier")
    variable: str = Field(..., description="Weather variable being forecast")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    longitude: float = Field(
        ..., ge=-180.0, le=180.0, description="Longitude in degrees"
    )
    initialization_time: datetime = Field(
        ..., description="When the forecast model was initialized"
    )
    lead_hours: int = Field(..., ge=0, le=384, description="Forecast lead time in hours")
    value: float = Field(..., description="Forecast value in the variable's unit")
    unit: str = Field(..., min_length=1, description="Unit of the forecast value")

    @field_validator("variable")
    @classmethod
    def validate_variable(cls, v: str) -> str:
        if v not in SUPPORTED_VARIABLES:
            raise ValueError(
                f"Unsupported variable '{v}'. Must be one of: {SUPPORTED_VARIABLES}"
            )
        return v

    @field_validator("value")
    @classmethod
    def validate_value_is_finite(cls, v: float) -> float:
        import math

        if math.isnan(v) or math.isinf(v):
            raise ValueError("Forecast value must be finite (not NaN or Inf)")
        return v


class Observation(BaseModel):
    """An observed weather value at a specific location and time.

    Used for verification — comparing forecasts against what actually happened.
    """

    variable: str = Field(..., description="Weather variable observed")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    valid_time: datetime = Field(..., description="When the observation was recorded")
    value: float = Field(..., description="Observed value")
    unit: str = Field(..., min_length=1)

    @field_validator("variable")
    @classmethod
    def validate_variable(cls, v: str) -> str:
        if v not in SUPPORTED_VARIABLES:
            raise ValueError(
                f"Unsupported variable '{v}'. Must be one of: {SUPPORTED_VARIABLES}"
            )
        return v

    @field_validator("value")
    @classmethod
    def validate_value_is_finite(cls, v: float) -> float:
        import math

        if math.isnan(v) or math.isinf(v):
            raise ValueError("Observation value must be finite (not NaN or Inf)")
        return v
