"""TASKS 013-015 — Blend, uncertainty, and explanation tests."""
from datetime import datetime, timezone

import pytest

from app.blending.engine import BlendEngine
from app.blending.explanation import ExplanationEngine
from app.core.constants import DisagreementLevel, UncertaintyLevel, WeatherRegimeType
from app.domain.forecast import Forecast
from app.domain.regime import WeatherRegime
from app.domain.uncertainty import DisagreementResult
from app.uncertainty.engine import UncertaintyEngine


def forecast(model_id: str, value: float, **overrides) -> Forecast:
    data = {
        "model_id": model_id,
        "variable": "temperature",
        "latitude": 19.076,
        "longitude": 72.8777,
        "initialization_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "lead_hours": 24,
        "value": value,
        "unit": "C",
    }
    data.update(overrides)
    return Forecast(**data)


def disagreement(std: float = 2.0) -> DisagreementResult:
    return DisagreementResult(
        mean=30.0,
        std=std,
        min_value=28.0,
        max_value=32.0,
        range=4.0,
        level=DisagreementLevel.MEDIUM,
        model_count=2,
    )


def test_blend_engine_calculates_weighted_average() -> None:
    result = BlendEngine().blend([forecast("ecmwf", 30.0), forecast("gfs", 36.0)], {"ecmwf": 3.0, "gfs": 1.0})

    assert result.value == pytest.approx(31.5)
    assert result.weights == pytest.approx({"ecmwf": 0.75, "gfs": 0.25})
    assert result.fallback_mode is False


def test_blend_engine_reports_single_model_fallback() -> None:
    result = BlendEngine().blend([forecast("ecmwf", 30.0)], {"ecmwf": 1.0})

    assert result.value == 30.0
    assert result.fallback_mode is True


@pytest.mark.parametrize(
    "forecasts,weights",
    [
        ([forecast("ecmwf", 30.0)], {"gfs": 1.0}),
        ([forecast("ecmwf", 30.0), forecast("gfs", 31.0, lead_hours=48)], {"ecmwf": 0.5, "gfs": 0.5}),
    ],
)
def test_blend_engine_rejects_invalid_target_or_weights(forecasts, weights) -> None:
    with pytest.raises(ValueError):
        BlendEngine().blend(forecasts, weights)


def test_uncertainty_combines_historical_error_and_spread() -> None:
    estimate = UncertaintyEngine().estimate(30.0, disagreement(2.0), historical_mae=1.0, recent_mae=0.5)

    assert estimate.lower_bound == 26.5
    assert estimate.upper_bound == 33.5
    assert estimate.level == UncertaintyLevel.MEDIUM


def test_uncertainty_rejects_negative_error() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        UncertaintyEngine().estimate(30.0, disagreement(), historical_mae=-1.0)


def test_explanation_reports_weights_regime_disagreement_and_range() -> None:
    regime = WeatherRegime(
        name=WeatherRegimeType.NORMAL,
        confidence=1.0,
        probabilities={item.value: 1.0 if item == WeatherRegimeType.NORMAL else 0.0 for item in WeatherRegimeType},
    )
    uncertainty = UncertaintyEngine().estimate(30.0, disagreement(), historical_mae=1.0)

    lines = ExplanationEngine().generate(
        {"ecmwf": 0.75, "gfs": 0.25}, regime, disagreement(), uncertainty
    )

    assert "ECMWF received the highest" in lines[0]
    assert "NORMAL" in lines[1]
    assert "MEDIUM" in lines[2]
    assert "not a calibrated confidence interval" in lines[3]
