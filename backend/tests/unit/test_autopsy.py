"""TASK 016 — Forecast autopsy tests."""
from datetime import datetime, timezone

import pytest

from app.core.constants import DisagreementLevel
from app.domain.forecast import Forecast, Observation
from app.domain.uncertainty import BlendResult, DisagreementResult
from app.verification.autopsy import ForecastAutopsyEngine


def source(model_id: str, value: float) -> Forecast:
    return Forecast(
        model_id=model_id,
        variable="precipitation",
        latitude=19.076,
        longitude=72.8777,
        initialization_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        lead_hours=24,
        value=value,
        unit="mm",
    )


def blend() -> BlendResult:
    return BlendResult(
        variable="precipitation",
        latitude=19.076,
        longitude=72.8777,
        valid_time="2026-01-02T00:00:00Z",
        blended_value=42.0,
        lower_bound=30.0,
        upper_bound=54.0,
        model_weights={"ecmwf": 0.7, "gfs": 0.3},
        disagreement=DisagreementResult(
            mean=40.0, std=5.0, min_value=35.0, max_value=45.0, range=10.0,
            level=DisagreementLevel.HIGH, model_count=2,
        ),
        regime="HEAVY_RAIN",
        regime_confidence=0.8,
        explanation=["Test explanation."],
        run_id="run-123",
    )


def observation(**overrides) -> Observation:
    data = {
        "variable": "precipitation",
        "latitude": 19.076,
        "longitude": 72.8777,
        "valid_time": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "value": 50.0,
        "unit": "mm",
    }
    data.update(overrides)
    return Observation(**data)


def test_autopsy_calculates_blend_and_per_model_errors() -> None:
    verification, autopsy = ForecastAutopsyEngine().analyze(blend(), [source("ecmwf", 45.0), source("gfs", 35.0)], observation())

    assert verification.error == -8.0
    assert verification.absolute_error == 8.0
    assert autopsy.model_errors == {"ecmwf": -5.0, "gfs": -15.0}
    assert "ECMWF had the smallest" in autopsy.assessment
    assert "underestimated" in autopsy.assessment


def test_autopsy_rejects_mismatched_observation_location() -> None:
    with pytest.raises(ValueError, match="location"):
        ForecastAutopsyEngine().analyze(blend(), [source("ecmwf", 45.0)], observation(latitude=20.0))


def test_autopsy_requires_source_forecasts() -> None:
    with pytest.raises(ValueError, match="source forecast"):
        ForecastAutopsyEngine().analyze(blend(), [], observation())
