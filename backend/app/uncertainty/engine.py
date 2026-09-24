"""Phase 1 forecast uncertainty ranges based on error and ensemble spread."""
from app.core.config import settings
from app.core.constants import UncertaintyLevel
from app.domain.uncertainty import DisagreementResult, UncertaintyEstimate


class UncertaintyEngine:
    """Estimate a range, not a statistically calibrated confidence interval."""

    def estimate(
        self,
        forecast_value: float,
        disagreement: DisagreementResult,
        *,
        historical_mae: float,
        recent_mae: float | None = None,
    ) -> UncertaintyEstimate:
        if historical_mae < 0.0 or (recent_mae is not None and recent_mae < 0.0):
            raise ValueError("Historical and recent MAE must be non-negative")
        scale = historical_mae + disagreement.std + (recent_mae or 0.0)
        relative_scale = scale / max(abs(forecast_value), 1.0)
        return UncertaintyEstimate(
            forecast_value=forecast_value,
            lower_bound=forecast_value - scale,
            upper_bound=forecast_value + scale,
            level=self._level(relative_scale),
        )

    @staticmethod
    def _level(relative_scale: float) -> UncertaintyLevel:
        if relative_scale < settings.DISAGREEMENT_LOW:
            return UncertaintyLevel.LOW
        if relative_scale < settings.DISAGREEMENT_MEDIUM:
            return UncertaintyLevel.MEDIUM
        if relative_scale < settings.DISAGREEMENT_HIGH:
            return UncertaintyLevel.HIGH
        return UncertaintyLevel.VERY_HIGH
