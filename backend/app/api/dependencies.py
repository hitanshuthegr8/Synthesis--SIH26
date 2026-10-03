from datetime import datetime, timezone

from fastapi import HTTPException

from ..core.config import settings, Settings
from ..domain.forecast import Forecast, Observation
from ..ingestion.csv_loader import generate_mock_observations
from ..ingestion.mock import MockForecastIngestor
from ..ingestion.scenarios import scenario_forecasts, scenario_observation
from ..skill.skill_engine import SimpleSkillEstimator

def get_settings() -> Settings:
    return settings


def require_demo_mode() -> None:
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=503, detail="No production forecast source is configured")


def demo_forecasts(variable: str, lead_hours: int, scenario: str | None = None) -> list[Forecast]:
    require_demo_mode()
    if scenario:
        forecasts = scenario_forecasts(scenario, lead_hours)
        if forecasts[0].variable != variable:
            raise HTTPException(status_code=422, detail=f"Scenario '{scenario}' requires variable '{forecasts[0].variable}'")
        return forecasts
    result = MockForecastIngestor(variables=(variable,), lead_hours=(lead_hours,)).ingest()
    if result.errors:
        raise HTTPException(status_code=422, detail=result.errors[0].reason)
    return result.valid_forecasts


def demo_observation(variable: str, lead_hours: int, scenario: str | None = None) -> Observation:
    if scenario:
        observation = scenario_observation(scenario, lead_hours)
        if observation.variable != variable:
            raise HTTPException(status_code=422, detail=f"Scenario '{scenario}' requires variable '{observation.variable}'")
        return observation
    forecasts = demo_forecasts(variable, lead_hours)
    source = forecasts[0]
    return generate_mock_observations(
        variables=(variable,), latitude=source.latitude, longitude=source.longitude,
        initialization_time=source.initialization_time, lead_hours=(lead_hours,),
    )[0]


def demo_skills(variable: str, lead_hours: int):
    require_demo_mode()
    forecasts: list[Forecast] = []
    observations: list[Observation] = []
    for day in range(1, 6):
        initialization_time = datetime(2025, 12, day, tzinfo=timezone.utc)
        batch = MockForecastIngestor(
            variables=(variable,), lead_hours=(lead_hours,), initialization_time=initialization_time, seed=day,
        ).ingest()
        forecasts.extend(batch.valid_forecasts)
        observations.extend(generate_mock_observations(
            variables=(variable,), latitude=19.076, longitude=72.8777,
            initialization_time=initialization_time, lead_hours=(lead_hours,), seed=day,
        ))
    return SimpleSkillEstimator().estimate_skills(forecasts, observations)
