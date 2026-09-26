"""Deterministic offline multi-model forecast generation for demo and tests."""
from datetime import datetime, timezone
from random import Random
from typing import Iterable

from app.core.constants import SUPPORTED_MODELS, SUPPORTED_VARIABLES, VARIABLE_UNITS
from app.core.config import settings
from app.ingestion.base import BaseForecastIngestor, IngestionBatchResult, process_forecast_batch


MODEL_BIASES = {"ecmwf": -0.3, "gfs": 0.8, "ai": 0.1, "gefs": 0.4}
MODEL_NOISE = {"ecmwf": 0.7, "gfs": 1.2, "ai": 0.9, "gefs": 1.0}
VARIABLE_BASELINES = {"temperature": 30.0, "precipitation": 12.0, "wind_speed": 7.0}


class MockForecastIngestor(BaseForecastIngestor):
    """Generate plausible, repeatable forecasts without a network dependency."""

    def __init__(
        self,
        *,
        models: Iterable[str] = SUPPORTED_MODELS,
        variables: Iterable[str] = SUPPORTED_VARIABLES,
        latitude: float = 19.0760,
        longitude: float = 72.8777,
        initialization_time: datetime | None = None,
        lead_hours: Iterable[int] = (24, 48, 72),
        seed: int = settings.RANDOM_SEED,
    ) -> None:
        self.models = tuple(models)
        self.variables = tuple(variables)
        self.latitude = latitude
        self.longitude = longitude
        self.initialization_time = initialization_time or datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.lead_hours = tuple(lead_hours)
        self.seed = seed

    def ingest(self) -> IngestionBatchResult:
        return process_forecast_batch(self.raw_records())

    def raw_records(self) -> list[dict[str, object]]:
        """Return raw records so callers can exercise the normal ingestion pipeline."""
        rng = Random(self.seed)
        records: list[dict[str, object]] = []
        for variable in self.variables:
            if variable not in VARIABLE_UNITS:
                raise ValueError(f"Unsupported mock variable: {variable}")
            for lead in self.lead_hours:
                if lead < 0:
                    raise ValueError("lead_hours must be non-negative")
                truth = _baseline_value(variable, lead)
                for model_id in self.models:
                    if model_id not in MODEL_BIASES:
                        raise ValueError(f"Unsupported mock model: {model_id}")
                    value = truth + MODEL_BIASES[model_id] + rng.gauss(0.0, MODEL_NOISE[model_id])
                    records.append(
                        {
                            "model_id": model_id,
                            "variable": variable,
                            "latitude": self.latitude,
                            "longitude": self.longitude,
                            "initialization_time": self.initialization_time,
                            "lead_hours": lead,
                            "value": _bounded_value(variable, value),
                            "unit": VARIABLE_UNITS[variable],
                        }
                    )
        return records


def _baseline_value(variable: str, lead_hours: int) -> float:
    """Small deterministic signal shared by all mock models."""
    cycle = ((lead_hours // 24) % 4) - 1.5
    if variable == "temperature":
        return VARIABLE_BASELINES[variable] + cycle * 0.6
    if variable == "precipitation":
        return VARIABLE_BASELINES[variable] + max(0.0, cycle) * 4.0
    return VARIABLE_BASELINES[variable] + cycle * 0.5


def _bounded_value(variable: str, value: float) -> float:
    if variable == "precipitation":
        return max(0.0, round(value, 4))
    if variable == "wind_speed":
        return max(0.0, round(value, 4))
    return round(value, 4)
