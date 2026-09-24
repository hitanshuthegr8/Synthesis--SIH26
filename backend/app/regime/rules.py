"""Transparent threshold rules for Phase 1 weather-regime classification."""
from dataclasses import dataclass

from app.core.config import settings
from app.core.constants import WeatherRegimeType


@dataclass(frozen=True)
class RegimeFeatures:
    """Aggregated, canonical-unit values used by the deterministic classifier."""

    temperature_c: float | None = None
    precipitation_mm: float | None = None
    wind_speed_ms: float | None = None


def regime_scores(features: RegimeFeatures) -> dict[WeatherRegimeType, float]:
    """Return non-negative rule strengths; larger values indicate a stronger match."""
    precipitation = features.precipitation_mm or 0.0
    temperature = features.temperature_c or float("-inf")
    wind_speed = features.wind_speed_ms or 0.0

    heavy_rain = precipitation / settings.REGIME_HEAVY_RAIN_MM
    heatwave = temperature / settings.REGIME_HEATWAVE_TEMP_C
    high_wind = wind_speed / settings.REGIME_HIGH_WIND_MS
    convective = min(
        precipitation / (settings.REGIME_HEAVY_RAIN_MM * 0.5),
        temperature / (settings.REGIME_HEATWAVE_TEMP_C * 0.75),
    )
    cyclonic = min(heavy_rain, high_wind)

    active_scores = {
        WeatherRegimeType.HEAVY_RAIN: max(0.0, heavy_rain) if precipitation >= settings.REGIME_HEAVY_RAIN_MM else 0.0,
        WeatherRegimeType.HEATWAVE: max(0.0, heatwave) if temperature >= settings.REGIME_HEATWAVE_TEMP_C else 0.0,
        WeatherRegimeType.HIGH_WIND: max(0.0, high_wind) if wind_speed >= settings.REGIME_HIGH_WIND_MS else 0.0,
        WeatherRegimeType.CONVECTIVE: max(0.0, convective * 1.1)
        if precipitation >= settings.REGIME_HEAVY_RAIN_MM * 0.5 and temperature >= settings.REGIME_HEATWAVE_TEMP_C * 0.75
        else 0.0,
        WeatherRegimeType.CYCLONIC: max(0.0, cyclonic * 1.2)
        if precipitation >= settings.REGIME_HEAVY_RAIN_MM and wind_speed >= settings.REGIME_HIGH_WIND_MS
        else 0.0,
    }
    active_scores[WeatherRegimeType.NORMAL] = 1.0 if not any(active_scores.values()) else 0.05
    return active_scores
