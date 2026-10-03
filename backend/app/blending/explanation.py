"""Deterministic plain-language explanations for a blend decision."""
from collections.abc import Mapping

from app.blending.contextual import ContextualAdjustment
from app.domain.regime import WeatherRegime
from app.domain.uncertainty import DisagreementResult, UncertaintyEstimate


class ExplanationEngine:
    """Describe the computed decision factors without asserting forecast superiority."""

    def generate(
        self,
        weights: Mapping[str, float],
        regime: WeatherRegime,
        disagreement: DisagreementResult,
        uncertainty: UncertaintyEstimate,
        adjustments: list[ContextualAdjustment] | None = None,
    ) -> list[str]:
        highest_model = max(weights, key=weights.__getitem__)
        lines = [
            f"{highest_model.upper()} received the highest calculated weight ({weights[highest_model]:.0%}) from the available skill inputs.",
            f"The primary weather regime is {regime.name.value} (rule score: {regime.confidence:.0%}).",
            f"Model disagreement is {disagreement.level.value} across {disagreement.model_count} model forecasts.",
            f"The forecast uncertainty range is {uncertainty.lower_bound:.2f} to {uncertainty.upper_bound:.2f}; it is not a calibrated confidence interval.",
        ]
        if adjustments:
            changed = [item for item in adjustments if item.regime_factor != 1.0 or item.recent_skill_factor != 1.0]
            if changed:
                strongest = max(changed, key=lambda item: item.adjusted_weight)
                lines.append(f"Contextual regime and recent-skill factors adjusted {strongest.model_id.upper()} to {strongest.adjusted_weight:.0%} weight.")
        return lines
