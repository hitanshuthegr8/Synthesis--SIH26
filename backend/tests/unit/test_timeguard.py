"""Phase 1.5 leakage-prevention tests."""
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.forecast import Forecast, Observation
from app.verification.timeguard import TimeGuard


def test_timeguard_rejects_future_forecast_initialization() -> None:
    as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
    forecast = Forecast(model_id="ecmwf", variable="temperature", latitude=19.0, longitude=72.0, initialization_time=as_of + timedelta(hours=1), lead_hours=24, value=30.0, unit="C")

    with pytest.raises(ValueError, match="Future forecast"):
        TimeGuard(as_of).allow_forecast(forecast)


def test_timeguard_rejects_future_observation() -> None:
    as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observation = Observation(variable="temperature", latitude=19.0, longitude=72.0, valid_time=as_of + timedelta(hours=1), value=30.0, unit="C")

    with pytest.raises(ValueError, match="Future observation"):
        TimeGuard(as_of).allow_observation(observation)
