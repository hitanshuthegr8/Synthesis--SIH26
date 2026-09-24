"""Core Phase 1 weighted forecast blending."""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.blending.weights import normalize_trust_scores
from app.domain.forecast import Forecast


@dataclass(frozen=True)
class CoreBlend:
    value: float
    weights: dict[str, float]
    fallback_mode: bool


class BlendEngine:
    """Produce a weighted average after validating a single forecast target."""

    def blend(self, forecasts: Sequence[Forecast], weights: Mapping[str, float]) -> CoreBlend:
        if not forecasts:
            raise ValueError("At least one forecast is required for blending")
        self._validate_target(forecasts)
        forecast_by_model = {forecast.model_id: forecast for forecast in forecasts}
        if len(forecast_by_model) != len(forecasts):
            raise ValueError("Only one forecast per model may be blended")
        if set(forecast_by_model) != set(weights):
            raise ValueError("Forecast models and weight models must match")

        normalized_weights = normalize_trust_scores(weights)
        value = sum(forecast_by_model[model_id].value * weight for model_id, weight in normalized_weights.items())
        return CoreBlend(
            value=value,
            weights=normalized_weights,
            fallback_mode=len(forecasts) == 1,
        )

    @staticmethod
    def _validate_target(forecasts: Sequence[Forecast]) -> None:
        first = forecasts[0]
        target = (
            first.variable,
            round(first.latitude, 4),
            round(first.longitude, 4),
            first.initialization_time,
            first.lead_hours,
        )
        for forecast in forecasts[1:]:
            current_target = (
                forecast.variable,
                round(forecast.latitude, 4),
                round(forecast.longitude, 4),
                forecast.initialization_time,
                forecast.lead_hours,
            )
            if current_target != target:
                raise ValueError("All forecasts must describe the same target")
