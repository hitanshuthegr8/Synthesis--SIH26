"""TASKS 017-018 — Chronological backtest and SQLite repository tests."""
from datetime import datetime, timezone

from app.core.constants import DisagreementLevel
from app.domain.forecast import Forecast, Observation
from app.domain.model import ModelSkill
from app.domain.uncertainty import BlendResult, DisagreementResult
from app.domain.verification import VerificationResult
from app.storage.database import SQLiteDatabase
from app.storage.repositories import SynthesisRepository
from app.verification.backtest import ChronologicalBacktestEngine


def forecast(model_id: str, value: float, initialization_time: datetime) -> Forecast:
    return Forecast(
        model_id=model_id, variable="temperature", latitude=19.076, longitude=72.8777,
        initialization_time=initialization_time, lead_hours=24, value=value, unit="C",
    )


def observation(value: float, valid_time: datetime) -> Observation:
    return Observation(
        variable="temperature", latitude=19.076, longitude=72.8777,
        valid_time=valid_time, value=value, unit="C",
    )


def test_backtest_runs_in_chronological_order_without_future_skill() -> None:
    first_init = datetime(2026, 1, 1, tzinfo=timezone.utc)
    second_init = datetime(2026, 1, 2, tzinfo=timezone.utc)
    forecasts = [
        forecast("ecmwf", 29.0, first_init), forecast("gfs", 34.0, first_init),
        forecast("ecmwf", 30.0, second_init), forecast("gfs", 36.0, second_init),
    ]
    observations = [observation(30.0, datetime(2026, 1, 2, tzinfo=timezone.utc)), observation(31.0, datetime(2026, 1, 3, tzinfo=timezone.utc))]

    result = ChronologicalBacktestEngine().run(forecasts, observations)

    assert len(result.blends) == 2
    assert result.blends[0].fallback_mode is True
    assert result.blends[0].model_weights == {"ecmwf": 0.5, "gfs": 0.5}
    assert result.blends[1].fallback_mode is False
    assert result.blends[1].model_weights["ecmwf"] > result.blends[1].model_weights["gfs"]
    assert result.verifications[1].error == result.blends[1].blended_value - 31.0


def test_backtest_skips_targets_without_an_observation() -> None:
    initial_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    result = ChronologicalBacktestEngine().run([forecast("ecmwf", 30.0, initial_time)], [])

    assert result.blends == []
    assert result.verifications == []


def test_sqlite_repository_round_trips_domain_objects(tmp_path) -> None:
    repository = SynthesisRepository(SQLiteDatabase(tmp_path / "synthesis.db"))
    initial_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    source_forecast = forecast("ecmwf", 30.0, initial_time)
    source_observation = observation(31.0, datetime(2026, 1, 2, tzinfo=timezone.utc))
    skill = ModelSkill(model_id="ecmwf", variable="temperature", lead_hours=24, metric="mae", score=1.0, sample_count=10)
    disagreement = DisagreementResult(mean=30.0, std=1.0, min_value=29.0, max_value=31.0, range=2.0, level=DisagreementLevel.LOW, model_count=1)
    blend = BlendResult(
        variable="temperature", latitude=19.076, longitude=72.8777, valid_time="2026-01-02T00:00:00Z",
        blended_value=30.0, lower_bound=28.0, upper_bound=32.0, model_weights={"ecmwf": 1.0},
        disagreement=disagreement, regime="NORMAL", regime_confidence=1.0, explanation=["test"], run_id="run-1",
    )
    verification = VerificationResult(
        run_id="run-1", variable="temperature", latitude=19.076, longitude=72.8777,
        valid_time=source_observation.valid_time, forecast_value=30.0, observation_value=31.0,
        error=-1.0, absolute_error=1.0, model_errors={"ecmwf": -1.0}, lead_hours=24,
    )

    repository.save_forecasts([source_forecast])
    repository.save_observations([source_observation])
    repository.save_model_skills([skill])
    repository.save_blend(blend)
    repository.save_verification(verification)

    assert repository.list_forecasts() == [source_forecast]
    assert repository.list_observations() == [source_observation]
    assert repository.list_model_skills() == [skill]
    assert repository.get_blend("run-1") == blend
    assert repository.get_verification("run-1") == verification
