"""Domain model for model skill and reliability.

Purpose:
    Represents the measured performance of a forecast model for a specific
    context (variable, region, lead time, season, regime).

Inputs:
    Historical forecast-observation pairs processed by the skill engine.

Outputs:
    ModelSkill objects with metric scores and sample counts.

Algorithm:
    Created by the skill/reliability engine from verification results.

Failure cases:
    - Negative sample_count raises ValidationError
    - NaN/Inf score raises ValidationError

Future replacement:
    Phase 2 may add hierarchical Bayesian skill estimation, but the
    ModelSkill domain object remains stable.
"""
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelSkill(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """Measured performance of a forecast model in a specific context.

    Every skill score MUST be accompanied by a sample_count so the
    reliability of the score itself can be assessed.
    """

    model_id: str = Field(..., min_length=1, description="Model identifier")
    variable: str = Field(..., description="Weather variable")
    region: str = Field(default="global", description="Geographic region identifier")
    lead_hours: int = Field(..., ge=0, description="Forecast lead time in hours")
    season: Optional[str] = Field(
        default=None, description="Season (DJF, MAM, JJA, SON) or None for all-season"
    )
    regime: Optional[str] = Field(
        default=None, description="Weather regime or None for all-regime"
    )
    metric: str = Field(..., description="Metric name (mae, rmse, bias)")
    score: float = Field(..., description="Metric score value")
    sample_count: int = Field(
        ..., ge=0, description="Number of forecast-observation pairs used"
    )

    @field_validator("score")
    @classmethod
    def validate_score_is_finite(cls, v: float) -> float:
        import math

        if math.isnan(v) or math.isinf(v):
            raise ValueError("Score must be finite (not NaN or Inf)")
        return v
