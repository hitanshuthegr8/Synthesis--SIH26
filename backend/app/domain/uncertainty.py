"""Domain model for uncertainty and disagreement.

Purpose:
    Represents model disagreement statistics and forecast uncertainty ranges.

Inputs:
    Multiple model forecasts for the same target.

Outputs:
    Disagreement metrics and uncertainty bounds.

Algorithm:
    Phase 1: spread-based disagreement + historical error uncertainty.
    Phase 2: conformal prediction, distributional forecasting.

Failure cases:
    - Upper bound < lower bound raises ValidationError
    - Negative std raises ValidationError

Future replacement:
    Phase 2 adds conformal prediction and CRPS-calibrated intervals.
    The UncertaintyEstimate domain object interface remains stable.
"""
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import DisagreementLevel, UncertaintyLevel


class DisagreementResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """Statistical summary of disagreement between forecast models.

    Measures how much the different forecast sources disagree about
    the same prediction target.
    """

    mean: float = Field(..., description="Mean of model forecasts")
    std: float = Field(..., ge=0.0, description="Standard deviation of forecasts")
    min_value: float = Field(..., description="Minimum forecast value")
    max_value: float = Field(..., description="Maximum forecast value")
    range: float = Field(..., ge=0.0, description="max - min")
    level: DisagreementLevel = Field(..., description="Categorical disagreement level")
    model_count: int = Field(..., ge=1, description="Number of models compared")


class UncertaintyEstimate(BaseModel):
    """Forecast uncertainty range.

    IMPORTANT: This is called 'forecast uncertainty range', NOT
    'confidence interval', unless actual statistical calibration
    has been performed and verified.
    """

    forecast_value: float = Field(..., description="Central forecast value")
    lower_bound: float = Field(..., description="Lower bound of uncertainty range")
    upper_bound: float = Field(..., description="Upper bound of uncertainty range")
    level: UncertaintyLevel = Field(..., description="Categorical uncertainty level")

    @model_validator(mode="after")
    def validate_bounds(self) -> "UncertaintyEstimate":
        if self.upper_bound < self.lower_bound:
            raise ValueError(
                f"Upper bound ({self.upper_bound}) must be >= "
                f"lower bound ({self.lower_bound})"
            )
        return self


class BlendResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """Complete result of the forecast blending process.

    This is the primary output of the SYNTHESIS engine, combining
    the blended forecast with weights, uncertainty, disagreement,
    regime, and explanation.
    """

    variable: str
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    valid_time: str = Field(..., description="ISO format datetime string")
    blended_value: float = Field(..., description="Weighted blended forecast")
    lower_bound: float = Field(..., description="Uncertainty lower bound")
    upper_bound: float = Field(..., description="Uncertainty upper bound")
    model_weights: dict[str, float] = Field(
        ..., description="Weight assigned to each model"
    )
    disagreement: DisagreementResult
    regime: str = Field(..., description="Primary weather regime name")
    regime_confidence: float = Field(..., ge=0.0, le=1.0)
    explanation: list[str] = Field(
        ..., description="List of explanation sentences"
    )
    fallback_mode: bool = Field(
        default=False,
        description="True if only one model was available",
    )
    run_id: str = Field(..., description="Unique run identifier for traceability")
    cycle_time: str = Field(default="", description="Forecast cycle timestamp")
    algorithm_version: str = Field(default="0.1.0", description="Blending algorithm version")
    dataset_version: str = Field(default="demo-v1", description="Input dataset version")
    config_hash: str = Field(default="", description="Configuration fingerprint")
    source_availability: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_weights_sum_to_one(self) -> "BlendResult":
        if self.model_weights:
            total = sum(self.model_weights.values())
            if abs(total - 1.0) > 0.01:
                raise ValueError(
                    f"Model weights must sum to ~1.0, got {total:.4f}"
                )
            for model_id, weight in self.model_weights.items():
                if weight < 0:
                    raise ValueError(
                        f"Weight for '{model_id}' is negative: {weight}"
                    )
        return self

    @model_validator(mode="after")
    def validate_uncertainty_bounds(self) -> "BlendResult":
        if self.upper_bound < self.lower_bound:
            raise ValueError(
                f"Upper bound ({self.upper_bound}) must be >= "
                f"lower bound ({self.lower_bound})"
            )
        return self
