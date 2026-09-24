"""Chronological, leakage-safe Phase 1 backtesting."""
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from app.blending.engine import BlendEngine
from app.blending.explanation import ExplanationEngine
from app.blending.weights import calculate_base_weights
from app.domain.forecast import Forecast, Observation
from app.domain.uncertainty import BlendResult
from app.domain.verification import VerificationResult
from app.regime.classifier import RuleBasedRegimeClassifier
from app.skill.skill_engine import SimpleSkillEstimator
from app.uncertainty.disagreement import DisagreementEngine
from app.uncertainty.engine import UncertaintyEngine
from app.verification.autopsy import ForecastAutopsyEngine


@dataclass(frozen=True)
class BacktestResult:
    blends: list[BlendResult]
    verifications: list[VerificationResult]


class ChronologicalBacktestEngine:
    """Blend historical forecasts without using observations from the future."""

    def run(self, forecasts: Sequence[Forecast], observations: Sequence[Observation]) -> BacktestResult:
        observation_index = {_observation_key(item): item for item in observations}
        grouped: dict[tuple[str, float, float, datetime, int], list[Forecast]] = defaultdict(list)
        for forecast in forecasts:
            grouped[_forecast_group_key(forecast)].append(forecast)

        blends: list[BlendResult] = []
        verifications: list[VerificationResult] = []
        for key, current_forecasts in sorted(grouped.items(), key=lambda item: _valid_time(item[1][0])):
            current_time = _valid_time(current_forecasts[0])
            observation = observation_index.get(_forecast_observation_key(current_forecasts[0]))
            if observation is None:
                continue

            historical_forecasts = [item for item in forecasts if _valid_time(item) < current_time]
            historical_observations = [item for item in observations if item.valid_time < current_time]
            skills = SimpleSkillEstimator().estimate_skills(historical_forecasts, historical_observations)
            current_skills = [
                item for item in skills
                if item.variable == current_forecasts[0].variable
                and item.lead_hours == current_forecasts[0].lead_hours
                and item.model_id in {forecast.model_id for forecast in current_forecasts}
                and item.metric == "mae"
            ]
            weights = calculate_base_weights(current_skills) if current_skills else _uniform_weights(current_forecasts)
            core_blend = BlendEngine().blend(current_forecasts, weights)
            disagreement = DisagreementEngine().calculate(current_forecasts)
            regime = RuleBasedRegimeClassifier().classify(current_forecasts)
            historical_mae = sum(item.score for item in current_skills) / len(current_skills) if current_skills else 0.0
            uncertainty = UncertaintyEngine().estimate(core_blend.value, disagreement, historical_mae=historical_mae)
            blend = BlendResult(
                variable=current_forecasts[0].variable,
                latitude=current_forecasts[0].latitude,
                longitude=current_forecasts[0].longitude,
                valid_time=current_time.isoformat().replace("+00:00", "Z"),
                blended_value=core_blend.value,
                lower_bound=uncertainty.lower_bound,
                upper_bound=uncertainty.upper_bound,
                model_weights=core_blend.weights,
                disagreement=disagreement,
                regime=regime.name.value,
                regime_confidence=regime.confidence,
                explanation=ExplanationEngine().generate(core_blend.weights, regime, disagreement, uncertainty),
                fallback_mode=core_blend.fallback_mode or not current_skills,
                run_id=f"backtest-{uuid4().hex}",
            )
            verification, _ = ForecastAutopsyEngine().analyze(blend, current_forecasts, observation)
            blends.append(blend)
            verifications.append(verification)
        return BacktestResult(blends=blends, verifications=verifications)


def _valid_time(forecast: Forecast) -> datetime:
    return forecast.initialization_time + timedelta(hours=forecast.lead_hours)


def _forecast_group_key(forecast: Forecast) -> tuple[str, float, float, datetime, int]:
    return (forecast.variable, round(forecast.latitude, 4), round(forecast.longitude, 4), forecast.initialization_time, forecast.lead_hours)


def _forecast_observation_key(forecast: Forecast) -> tuple[str, float, float, datetime]:
    return (forecast.variable, round(forecast.latitude, 4), round(forecast.longitude, 4), _valid_time(forecast))


def _observation_key(observation: Observation) -> tuple[str, float, float, datetime]:
    return (observation.variable, round(observation.latitude, 4), round(observation.longitude, 4), observation.valid_time)


def _uniform_weights(forecasts: Sequence[Forecast]) -> dict[str, float]:
    return {forecast.model_id: 1.0 / len(forecasts) for forecast in forecasts}
