"""TASKS 009-010 — Regime classification and disagreement tests."""
from datetime import datetime, timezone

import pytest

from app.core.constants import DisagreementLevel, WeatherRegimeType
from app.domain.forecast import Forecast
from app.regime.classifier import RuleBasedRegimeClassifier
from app.regime.rules import RegimeFeatures
from app.uncertainty.disagreement import DisagreementEngine


def make_forecast(variable: str, value: float, model_id: str = "ecmwf") -> Forecast:
    units = {"temperature": "C", "precipitation": "mm", "wind_speed": "m/s"}
    return Forecast(
        model_id=model_id,
        variable=variable,
        latitude=19.076,
        longitude=72.8777,
        initialization_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        lead_hours=24,
        value=value,
        unit=units[variable],
    )


def test_normal_regime_has_full_probability_vector() -> None:
    regime = RuleBasedRegimeClassifier().classify_features(RegimeFeatures(temperature_c=30.0, precipitation_mm=5.0, wind_speed_ms=4.0))

    assert regime.name == WeatherRegimeType.NORMAL
    assert regime.confidence == 1.0
    assert set(regime.probabilities) == {item.value for item in WeatherRegimeType}
    assert sum(regime.probabilities.values()) == pytest.approx(1.0)


def test_heatwave_regime_uses_configured_temperature_threshold() -> None:
    regime = RuleBasedRegimeClassifier().classify([make_forecast("temperature", 42.0)])

    assert regime.name == WeatherRegimeType.HEATWAVE
    assert regime.probabilities["HEATWAVE"] > regime.probabilities["NORMAL"]


def test_cyclonic_rule_takes_precedence_for_heavy_rain_and_wind() -> None:
    regime = RuleBasedRegimeClassifier().classify_features(
        RegimeFeatures(temperature_c=28.0, precipitation_mm=80.0, wind_speed_ms=30.0)
    )

    assert regime.name == WeatherRegimeType.CYCLONIC
    assert regime.confidence == regime.probabilities["CYCLONIC"]


def test_classifier_requires_forecasts() -> None:
    with pytest.raises(ValueError, match="At least one forecast"):
        RuleBasedRegimeClassifier().classify([])


def test_equal_models_have_zero_disagreement() -> None:
    forecasts = [make_forecast("temperature", 30.0, model_id) for model_id in ("ecmwf", "gfs", "ai")]

    result = DisagreementEngine().calculate(forecasts)

    assert result.std == 0.0
    assert result.range == 0.0
    assert result.level == DisagreementLevel.LOW
    assert result.coefficient_of_variation == 0.0


def test_disagreement_reports_spread_statistics_and_level() -> None:
    forecasts = [make_forecast("precipitation", value, model_id) for value, model_id in ((18.0, "ecmwf"), (25.0, "gfs"), (42.0, "ai"))]

    result = DisagreementEngine().calculate(forecasts)

    assert result.mean == pytest.approx(85 / 3)
    assert result.median == 25.0
    assert result.range == 24.0
    assert result.level == DisagreementLevel.EXTREME


def test_disagreement_rejects_mixed_variables() -> None:
    with pytest.raises(ValueError, match="one variable"):
        DisagreementEngine().calculate([make_forecast("temperature", 30.0), make_forecast("wind_speed", 5.0)])
