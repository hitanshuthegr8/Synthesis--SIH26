"""Named synthetic demo scenarios. These are never presented as observations."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.constants import VARIABLE_UNITS
from app.domain.forecast import Forecast, Observation


@dataclass(frozen=True)
class DemoScenario:
    name: str
    variable: str
    values: dict[str, float]
    observation_value: float


SCENARIOS = {
    "normal": DemoScenario("normal", "temperature", {"ecmwf": 31.2, "gfs": 30.8, "ai": 31.4, "gefs": 30.9}, 31.1),
    "heavy_rain": DemoScenario("heavy_rain", "precipitation", {"ecmwf": 48.0, "gfs": 21.0, "ai": 57.0, "gefs": 29.0}, 52.0),
    "model_conflict": DemoScenario("model_conflict", "precipitation", {"ecmwf": 20.0, "gfs": 85.0, "ai": 31.0, "gefs": 77.0}, 29.0),
}


def get_scenario(name: str) -> DemoScenario:
    try:
        return SCENARIOS[name]
    except KeyError as error:
        raise ValueError(f"Unknown demo scenario: {name}") from error


def scenario_forecasts(name: str, lead_hours: int) -> list[Forecast]:
    scenario = get_scenario(name)
    initialization_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Forecast(
            model_id=model_id, variable=scenario.variable, latitude=19.076, longitude=72.8777,
            initialization_time=initialization_time, lead_hours=lead_hours, value=value,
            unit=VARIABLE_UNITS[scenario.variable],
        )
        for model_id, value in scenario.values.items()
    ]


def scenario_observation(name: str, lead_hours: int) -> Observation:
    scenario = get_scenario(name)
    return Observation(
        variable=scenario.variable, latitude=19.076, longitude=72.8777,
        valid_time=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=lead_hours),
        value=scenario.observation_value, unit=VARIABLE_UNITS[scenario.variable],
    )
