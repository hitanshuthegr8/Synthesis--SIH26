"""Deterministic and explainable Phase 1 weather-regime classifier."""
from collections import defaultdict
from collections.abc import Sequence

from app.domain.forecast import Forecast
from app.domain.regime import WeatherRegime
from app.regime.rules import RegimeFeatures, regime_scores


class RuleBasedRegimeClassifier:
    """Classify ensemble-mean conditions using versionable threshold rules."""

    def classify(self, forecasts: Sequence[Forecast]) -> WeatherRegime:
        if not forecasts:
            raise ValueError("At least one forecast is required for regime classification")

        values: dict[str, list[float]] = defaultdict(list)
        for forecast in forecasts:
            values[forecast.variable].append(forecast.value)
        features = RegimeFeatures(
            temperature_c=_mean_or_none(values["temperature"]),
            # Precipitation regimes are impact-sensitive: a credible high-end
            # member should remain visible instead of being averaged away.
            precipitation_mm=max(values["precipitation"]) if values["precipitation"] else None,
            wind_speed_ms=_mean_or_none(values["wind_speed"]),
        )
        return self.classify_features(features)

    def classify_features(self, features: RegimeFeatures) -> WeatherRegime:
        scores = regime_scores(features)
        total = sum(scores.values())
        probabilities = {regime.value: score / total for regime, score in scores.items()}
        primary = max(scores, key=scores.__getitem__)
        return WeatherRegime(
            name=primary,
            confidence=probabilities[primary.value],
            probabilities=probabilities,
        )


def _mean_or_none(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None
