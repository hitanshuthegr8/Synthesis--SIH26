"""Demonstrate that future observations must not inflate apparent skill."""
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.forecast import Forecast, Observation
from app.skill.skill_engine import SimpleSkillEstimator
from app.verification.timeguard import TimeGuard


def _forecast(model_id: str, init: datetime, lead: int, value: float) -> Forecast:
    return Forecast(
        model_id=model_id,
        variable="temperature",
        latitude=19.0,
        longitude=73.0,
        initialization_time=init,
        lead_hours=lead,
        value=value,
        unit="C",
    )


def _observation(valid: datetime, value: float) -> Observation:
    return Observation(
        variable="temperature",
        latitude=19.0,
        longitude=73.0,
        valid_time=valid,
        value=value,
        unit="C",
    )


def test_timeguard_blocks_future_observation_for_skill_window() -> None:
    as_of = datetime(2026, 1, 2, tzinfo=timezone.utc)
    guard = TimeGuard(as_of=as_of)
    future_obs = _observation(datetime(2026, 1, 5, tzinfo=timezone.utc), 30.0)
    try:
        guard.allow_observation(future_obs)
        leaked = True
    except ValueError:
        leaked = False
    assert not leaked


def test_leaky_skill_uses_future_observation_and_changes_scores() -> None:
    init_early = datetime(2026, 1, 1, tzinfo=timezone.utc)
    init_late = datetime(2026, 1, 4, tzinfo=timezone.utc)
    forecast_early = _forecast("ecmwf", init_early, 24, 31.0)
    forecast_late = _forecast("ecmwf", init_late, 24, 35.0)
    obs_early = _observation(init_early + timedelta(hours=24), 30.0)
    obs_late = _observation(init_late + timedelta(hours=24), 30.0)

    # Correct as-of Jan 2: only the first forecast/observation pair is valid.
    safe_skills = SimpleSkillEstimator().estimate_skills([forecast_early], [obs_early])
    # Leaky configuration: future verification pairs enter the same skill pool.
    leaky_skills = SimpleSkillEstimator().estimate_skills(
        [forecast_early, forecast_late], [obs_early, obs_late]
    )

    safe_mae = next(item.score for item in safe_skills if item.model_id == "ecmwf" and item.metric == "mae")
    leaky_mae = next(item.score for item in leaky_skills if item.model_id == "ecmwf" and item.metric == "mae")
    assert safe_mae == pytest.approx(1.0)
    assert leaky_mae == pytest.approx(3.0)
    assert leaky_mae > safe_mae
