"""TASKS 005-008 — Offline data generation, metrics, and reliability tests."""
from datetime import datetime, timezone

import pytest

from app.domain.model import ModelSkill
from app.ingestion.csv_loader import generate_mock_observations, load_observations_csv
from app.ingestion.mock import MockForecastIngestor
from app.skill.metrics import calculate_bias, calculate_mae, calculate_rmse, calculate_skill_metrics
from app.skill.reliability import ReliabilityEngine
from app.skill.skill_engine import SimpleSkillEstimator


def test_mock_ingestor_is_repeatable_and_multimodel() -> None:
    first = MockForecastIngestor(variables=("temperature",), lead_hours=(24,), seed=7).ingest()
    second = MockForecastIngestor(variables=("temperature",), lead_hours=(24,), seed=7).ingest()

    assert first.errors == []
    assert len(first.valid_forecasts) == 4
    assert [item.model_dump() for item in first.valid_forecasts] == [
        item.model_dump() for item in second.valid_forecasts
    ]
    assert {item.model_id for item in first.valid_forecasts} == {"ecmwf", "gfs", "ai", "gefs"}


def test_mock_ingestor_rejects_unsupported_model() -> None:
    with pytest.raises(ValueError, match="Unsupported mock model"):
        MockForecastIngestor(models=("unknown",)).raw_records()


def test_mock_observations_align_with_forecast_grid() -> None:
    initial_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observations = generate_mock_observations(
        variables=("temperature", "wind_speed"),
        latitude=19.076,
        longitude=72.8777,
        initialization_time=initial_time,
        lead_hours=(24, 48),
    )

    assert len(observations) == 4
    assert observations[0].valid_time == datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert {item.unit for item in observations} == {"C", "m/s"}


def test_csv_loader_normalizes_units(tmp_path) -> None:
    csv_file = tmp_path / "observations.csv"
    csv_file.write_text(
        "variable,latitude,longitude,valid_time,value,unit\n"
        "temperature,19.076,72.8777,2026-01-02T00:00:00Z,86,F\n"
        "precipitation,19.076,72.8777,2026-01-02T00:00:00Z,1,in\n",
        encoding="utf-8",
    )

    observations = load_observations_csv(csv_file)

    assert [(item.value, item.unit) for item in observations] == [(30.0, "C"), (25.4, "mm")]


def test_csv_loader_rejects_missing_columns(tmp_path) -> None:
    csv_file = tmp_path / "incomplete.csv"
    csv_file.write_text("variable,value\ntemperature,20\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must include"):
        load_observations_csv(csv_file)


def test_error_metrics() -> None:
    predictions = [1.0, 3.0, 8.0]
    observations = [2.0, 1.0, 5.0]

    assert calculate_mae(predictions, observations) == 2.0
    assert calculate_rmse(predictions, observations) == pytest.approx((14 / 3) ** 0.5)
    assert calculate_bias(predictions, observations) == pytest.approx(4 / 3)
    assert calculate_skill_metrics(predictions, observations).sample_count == 3


@pytest.mark.parametrize(
    "predictions,observations",
    [([], []), ([1.0], []), ([float("nan")], [1.0])],
)
def test_metrics_reject_invalid_pairs(predictions, observations) -> None:
    with pytest.raises(ValueError):
        calculate_skill_metrics(predictions, observations)


def test_simple_skill_estimator_matches_valid_times() -> None:
    ingestor = MockForecastIngestor(variables=("temperature",), lead_hours=(24, 48), seed=2)
    forecasts = ingestor.ingest().valid_forecasts
    observations = generate_mock_observations(
        variables=("temperature",),
        latitude=ingestor.latitude,
        longitude=ingestor.longitude,
        initialization_time=ingestor.initialization_time,
        lead_hours=(24, 48),
        seed=2,
    )

    skills = SimpleSkillEstimator().estimate_skills(forecasts, observations)

    assert len(skills) == 24
    assert {item.metric for item in skills} == {"mae", "rmse", "bias"}
    assert {item.sample_count for item in skills} == {1}


def test_reliability_uses_only_models_with_sufficient_samples() -> None:
    skills = [
        ModelSkill(model_id="ecmwf", variable="temperature", lead_hours=24, metric="mae", score=1.0, sample_count=30),
        ModelSkill(model_id="gfs", variable="temperature", lead_hours=24, metric="mae", score=2.0, sample_count=30),
        ModelSkill(model_id="ai", variable="temperature", lead_hours=24, metric="mae", score=0.5, sample_count=2),
    ]

    estimates = ReliabilityEngine(minimum_samples=30).estimate(skills)
    by_model = {item.model_id: item for item in estimates}

    assert by_model["ecmwf"].reliability == pytest.approx(2 / 3)
    assert by_model["gfs"].reliability == pytest.approx(1 / 3)
    assert by_model["ai"].reliability == 0.0
    assert by_model["ai"].sufficient_samples is False
