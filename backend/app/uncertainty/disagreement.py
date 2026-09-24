"""Configuration-driven ensemble disagreement statistics."""
import math
from collections.abc import Sequence
from statistics import fmean, median, pstdev

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.constants import DisagreementLevel, EPSILON
from app.domain.forecast import Forecast
from app.domain.uncertainty import DisagreementResult


class DetailedDisagreementResult(DisagreementResult):
    """Disagreement output with additional statistics useful to later engines."""

    median: float
    coefficient_of_variation: float | None = Field(default=None, ge=0.0)


class DisagreementEngine:
    """Measure spread among forecasts for one variable and one target context."""

    def calculate(self, forecasts: Sequence[Forecast]) -> DetailedDisagreementResult:
        if not forecasts:
            raise ValueError("At least one forecast is required for disagreement")
        variables = {forecast.variable for forecast in forecasts}
        if len(variables) != 1:
            raise ValueError("Disagreement can only compare forecasts for one variable")

        values = [forecast.value for forecast in forecasts]
        mean = fmean(values)
        std = pstdev(values) if len(values) > 1 else 0.0
        value_range = max(values) - min(values)
        coefficient_of_variation = std / abs(mean) if abs(mean) > EPSILON else None
        return DetailedDisagreementResult(
            mean=mean,
            median=median(values),
            std=std,
            min_value=min(values),
            max_value=max(values),
            range=value_range,
            coefficient_of_variation=coefficient_of_variation,
            level=self._level(value_range, mean),
            model_count=len(values),
        )

    @staticmethod
    def _level(value_range: float, mean: float) -> DisagreementLevel:
        """Classify relative spread where a relative denominator is meaningful."""
        scale = abs(mean) if abs(mean) > EPSILON else 1.0
        relative_range = value_range / scale
        if relative_range < settings.DISAGREEMENT_LOW:
            return DisagreementLevel.LOW
        if relative_range < settings.DISAGREEMENT_MEDIUM:
            return DisagreementLevel.MEDIUM
        if relative_range < settings.DISAGREEMENT_HIGH:
            return DisagreementLevel.HIGH
        return DisagreementLevel.EXTREME
