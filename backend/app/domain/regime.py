"""Domain model for weather regimes.

Purpose:
    Represents the classified weather regime for a forecast context,
    including per-regime probability distribution.

Inputs:
    Forecast data analyzed by the regime classifier.

Outputs:
    WeatherRegime with primary regime, confidence, and full probability vector.

Algorithm:
    Phase 1 uses deterministic threshold-based classification.
    Phase 2 may use a soft probabilistic classifier.

Failure cases:
    - Probabilities that don't sum to ~1.0 raise ValidationError
    - Negative probabilities raise ValidationError
    - Confidence outside [0, 1] raises ValidationError

Future replacement:
    Phase 2 ContextualMoE may subsume regime classification, but the
    WeatherRegime domain object remains the interface.
"""
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import WeatherRegimeType


class WeatherRegime(BaseModel):
    """Classified weather regime with probability distribution.

    The regime engine always returns a full probability vector over all
    regime types, enabling soft-regime blending in Phase 2.
    """

    name: WeatherRegimeType = Field(
        ..., description="Primary (most probable) weather regime"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in the primary regime"
    )
    probabilities: dict[str, float] = Field(
        ..., description="Probability for each regime type"
    )

    @field_validator("probabilities")
    @classmethod
    def validate_probabilities(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("Probabilities cannot be empty")
        for regime_name, prob in v.items():
            if prob < 0.0:
                raise ValueError(
                    f"Probability for '{regime_name}' is negative: {prob}"
                )
        total = sum(v.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Probabilities must sum to ~1.0, got {total:.4f}"
            )
        return v

    @model_validator(mode="after")
    def validate_confidence_matches_primary(self) -> "WeatherRegime":
        """Ensure confidence matches the probability of the primary regime."""
        primary_key = self.name.value
        if primary_key in self.probabilities:
            if abs(self.confidence - self.probabilities[primary_key]) > 0.01:
                raise ValueError(
                    f"Confidence ({self.confidence}) doesn't match "
                    f"primary regime probability ({self.probabilities[primary_key]})"
                )
        return self
