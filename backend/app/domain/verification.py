"""Domain model for verification results.

Purpose:
    Represents the result of comparing a forecast against an observation
    (forecast autopsy) and stores error metrics per model.

Inputs:
    Forecast-observation pairs after verification time has passed.

Outputs:
    VerificationResult with per-model and blend errors.

Failure cases:
    - NaN/Inf errors raise ValidationError

Future replacement:
    Phase 2 may add CRPS, threshold-weighted CRPS, and reliability diagrams,
    but the base VerificationResult remains stable.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VerificationResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """Result of comparing a single forecast against its observation."""

    run_id: str = Field(..., description="Unique identifier for the forecast run")
    variable: str = Field(..., description="Weather variable")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    valid_time: datetime = Field(..., description="Verification time")
    forecast_value: float = Field(..., description="Blended forecast value")
    observation_value: float = Field(..., description="Observed value")
    error: float = Field(..., description="forecast - observation")
    absolute_error: float = Field(..., ge=0.0, description="|forecast - observation|")
    model_errors: dict[str, float] = Field(
        default_factory=dict,
        description="Per-model errors: {model_id: forecast - observation}",
    )
    regime: Optional[str] = Field(default=None, description="Weather regime at verification time")
    lead_hours: int = Field(..., ge=0, description="Lead time of the forecast")

    @field_validator("error", "forecast_value", "observation_value")
    @classmethod
    def validate_finite(cls, v: float) -> float:
        import math

        if math.isnan(v) or math.isinf(v):
            raise ValueError("Value must be finite")
        return v


class ForecastAutopsy(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """Detailed post-mortem analysis of a forecast event.

    Combines verification results with model comparison and regime context
    to produce a diagnostic summary.
    """

    run_id: str = Field(..., description="Forecast run identifier")
    variable: str
    valid_time: datetime
    forecast_value: float = Field(..., description="SYNTHESIS blend value")
    observation_value: float = Field(..., description="Observed value")
    blend_error: float = Field(..., description="Blend forecast - observation")
    model_forecasts: dict[str, float] = Field(
        ..., description="Each model's original forecast"
    )
    model_errors: dict[str, float] = Field(
        ..., description="Each model's error against observation"
    )
    regime: Optional[str] = Field(default=None)
    assessment: str = Field(
        ..., description="Machine-generated diagnostic assessment"
    )
