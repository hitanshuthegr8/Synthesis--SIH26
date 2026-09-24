"""Bounded, explainable Phase 1 adjustments to base model weights."""
from collections.abc import Mapping
from pydantic import BaseModel, Field

from app.blending.weights import normalize_trust_scores
from app.core.constants import DisagreementLevel


class ContextualAdjustment(BaseModel):
    model_id: str
    base_weight: float = Field(ge=0.0)
    regime_factor: float = Field(gt=0.0)
    recent_skill_factor: float = Field(gt=0.0)
    disagreement_factor: float = Field(gt=0.0)
    adjusted_weight: float = Field(ge=0.0)


class ContextualWeightAdjuster:
    """Apply capped relative-error modifiers, then normalize to a valid simplex."""

    def adjust(
        self,
        base_weights: Mapping[str, float],
        *,
        base_mae: Mapping[str, float],
        regime_mae: Mapping[str, float] | None = None,
        recent_mae: Mapping[str, float] | None = None,
        disagreement: DisagreementLevel = DisagreementLevel.LOW,
    ) -> tuple[dict[str, float], list[ContextualAdjustment]]:
        if set(base_weights) != set(base_mae):
            raise ValueError("base_weights and base_mae must cover the same models")

        regime_mae = regime_mae or {}
        recent_mae = recent_mae or {}
        equal_weight = 1.0 / len(base_weights)
        raw_scores: dict[str, float] = {}
        factors: dict[str, tuple[float, float, float]] = {}
        for model_id, base_weight in base_weights.items():
            regime_factor = _relative_error_factor(base_mae[model_id], regime_mae.get(model_id))
            recent_factor = _relative_error_factor(base_mae[model_id], recent_mae.get(model_id))
            disagreement_factor = _disagreement_factor(base_weight, equal_weight, disagreement)
            factors[model_id] = (regime_factor, recent_factor, disagreement_factor)
            raw_scores[model_id] = base_weight * regime_factor * recent_factor * disagreement_factor

        adjusted_weights = normalize_trust_scores(raw_scores)
        adjustments = [
            ContextualAdjustment(
                model_id=model_id,
                base_weight=base_weights[model_id],
                regime_factor=factors[model_id][0],
                recent_skill_factor=factors[model_id][1],
                disagreement_factor=factors[model_id][2],
                adjusted_weight=adjusted_weights[model_id],
            )
            for model_id in sorted(base_weights)
        ]
        return adjusted_weights, adjustments


def _relative_error_factor(base_error: float, contextual_error: float | None) -> float:
    if base_error < 0.0 or (contextual_error is not None and contextual_error < 0.0):
        raise ValueError("MAE values must be non-negative")
    if contextual_error is None:
        return 1.0
    return min(1.5, max(0.5, (base_error + 1e-10) / (contextual_error + 1e-10)))


def _disagreement_factor(
    base_weight: float, equal_weight: float, level: DisagreementLevel
) -> float:
    """Under high spread, move weights modestly toward equal weighting."""
    pull_strength = {
        DisagreementLevel.LOW: 0.0,
        DisagreementLevel.MEDIUM: 0.1,
        DisagreementLevel.HIGH: 0.2,
        DisagreementLevel.EXTREME: 0.35,
    }[level]
    target_weight = base_weight * (1.0 - pull_strength) + equal_weight * pull_strength
    return target_weight / max(base_weight, 1e-10)
