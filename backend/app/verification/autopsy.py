"""Traceable post-verification analysis for one completed forecast run."""
from datetime import datetime
from collections.abc import Sequence

from app.domain.forecast import Forecast, Observation
from app.domain.uncertainty import BlendResult
from app.domain.verification import ForecastAutopsy, VerificationResult


class ForecastAutopsyEngine:
    """Compare a completed blend and its components with the matching observation."""

    def analyze(
        self, blend: BlendResult, forecasts: Sequence[Forecast], observation: Observation
    ) -> tuple[VerificationResult, ForecastAutopsy]:
        self._validate_inputs(blend, forecasts, observation)
        model_forecasts = {forecast.model_id: forecast.value for forecast in forecasts}
        model_errors = {model_id: value - observation.value for model_id, value in model_forecasts.items()}
        blend_error = blend.blended_value - observation.value
        valid_time = datetime.fromisoformat(blend.valid_time.replace("Z", "+00:00"))
        verification = VerificationResult(
            run_id=blend.run_id,
            variable=blend.variable,
            latitude=blend.latitude,
            longitude=blend.longitude,
            valid_time=valid_time,
            forecast_value=blend.blended_value,
            observation_value=observation.value,
            error=blend_error,
            absolute_error=abs(blend_error),
            model_errors=model_errors,
            regime=blend.regime,
            lead_hours=forecasts[0].lead_hours,
        )
        autopsy = ForecastAutopsy(
            run_id=blend.run_id,
            variable=blend.variable,
            valid_time=valid_time,
            forecast_value=blend.blended_value,
            observation_value=observation.value,
            blend_error=blend_error,
            model_forecasts=model_forecasts,
            model_errors=model_errors,
            regime=blend.regime,
            assessment=self._assessment(blend_error, model_errors),
        )
        return verification, autopsy

    @staticmethod
    def _validate_inputs(blend: BlendResult, forecasts: Sequence[Forecast], observation: Observation) -> None:
        if not forecasts:
            raise ValueError("At least one source forecast is required for an autopsy")
        if observation.variable != blend.variable or any(item.variable != blend.variable for item in forecasts):
            raise ValueError("Blend, forecasts, and observation must use the same variable")
        if round(observation.latitude, 4) != round(blend.latitude, 4) or round(observation.longitude, 4) != round(blend.longitude, 4):
            raise ValueError("Observation location does not match the blend")

    @staticmethod
    def _assessment(blend_error: float, model_errors: dict[str, float]) -> str:
        best_model = min(model_errors, key=lambda model_id: abs(model_errors[model_id]))
        direction = "underestimated" if blend_error < 0.0 else "overestimated" if blend_error > 0.0 else "matched"
        all_under = all(error < 0.0 for error in model_errors.values())
        all_over = all(error > 0.0 for error in model_errors.values())
        consensus = " All source models underestimated the event." if all_under else " All source models overestimated the event." if all_over else " Source-model errors were mixed."
        return f"The blend {direction} the observation by {abs(blend_error):.2f}. {best_model.upper()} had the smallest source-model absolute error.{consensus}"
