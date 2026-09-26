"""Runtime guard against future-information leakage in forecast computation."""
from datetime import datetime

from app.domain.forecast import Forecast, Observation


class TimeGuard:
    """Ensure an analysis only uses data that was available at its as-of time."""

    def __init__(self, as_of: datetime) -> None:
        self.as_of = as_of

    def allow_forecast(self, forecast: Forecast) -> None:
        if forecast.initialization_time > self.as_of:
            raise ValueError("Future forecast initialization is unavailable at this analysis time")

    def allow_observation(self, observation: Observation) -> None:
        if observation.valid_time > self.as_of:
            raise ValueError("Future observation is unavailable at this analysis time")
