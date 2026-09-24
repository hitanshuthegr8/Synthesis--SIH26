"""Interpretable Phase 1 historical skill estimation."""
from collections import defaultdict
from datetime import timedelta
from typing import Protocol, Sequence

from app.domain.forecast import Forecast, Observation
from app.domain.model import ModelSkill
from app.skill.metrics import calculate_skill_metrics


class SkillEstimator(Protocol):
    def estimate_skills(
        self, forecasts: Sequence[Forecast], observations: Sequence[Observation]
    ) -> list[ModelSkill]: ...


class SimpleSkillEstimator:
    """Match forecast valid times to observations and calculate MAE, RMSE, and bias."""

    def estimate_skills(
        self, forecasts: Sequence[Forecast], observations: Sequence[Observation]
    ) -> list[ModelSkill]:
        observation_index = {_observation_key(item): item for item in observations}
        paired: dict[tuple[str, str, int], list[tuple[float, float]]] = defaultdict(list)
        for forecast in forecasts:
            observation = observation_index.get(_forecast_key(forecast))
            if observation is not None:
                paired[(forecast.model_id, forecast.variable, forecast.lead_hours)].append(
                    (forecast.value, observation.value)
                )

        skills: list[ModelSkill] = []
        for (model_id, variable, lead_hours), pairs in sorted(paired.items()):
            metrics = calculate_skill_metrics(
                [prediction for prediction, _ in pairs], [observation for _, observation in pairs]
            )
            for metric, score in (("mae", metrics.mae), ("rmse", metrics.rmse), ("bias", metrics.bias)):
                skills.append(
                    ModelSkill(
                        model_id=model_id,
                        variable=variable,
                        lead_hours=lead_hours,
                        metric=metric,
                        score=score,
                        sample_count=metrics.sample_count,
                    )
                )
        return skills


def _forecast_key(forecast: Forecast) -> tuple[str, float, float, object]:
    return (
        forecast.variable,
        round(forecast.latitude, 4),
        round(forecast.longitude, 4),
        forecast.initialization_time + timedelta(hours=forecast.lead_hours),
    )


def _observation_key(observation: Observation) -> tuple[str, float, float, object]:
    return (
        observation.variable,
        round(observation.latitude, 4),
        round(observation.longitude, 4),
        observation.valid_time,
    )
