"""Canonical offline source adapters for the four Phase 1.5 benchmark sources."""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from pydantic import BaseModel, Field, model_validator

from app.domain.forecast import Forecast
from app.ingestion.scenarios import scenario_forecasts


class ForecastRecord(BaseModel):
    """A source-neutral forecast value keyed to a canonical demo grid cell."""

    source_id: str = Field(min_length=1)
    initialization_time: datetime
    valid_time: datetime
    lead_hours: int = Field(ge=0, le=384)
    variable: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    cell_id: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    quality_flag: str = "synthetic_benchmark"

    @model_validator(mode="after")
    def valid_time_matches_lead(self) -> "ForecastRecord":
        expected = self.initialization_time + timedelta(hours=self.lead_hours)
        if self.valid_time != expected:
            raise ValueError("valid_time must equal initialization_time plus lead_hours")
        return self

    @classmethod
    def from_forecast(cls, forecast: Forecast) -> "ForecastRecord":
        return cls(
            source_id=forecast.model_id,
            initialization_time=forecast.initialization_time,
            valid_time=forecast.initialization_time + timedelta(hours=forecast.lead_hours),
            lead_hours=forecast.lead_hours,
            variable=forecast.variable,
            latitude=forecast.latitude,
            longitude=forecast.longitude,
            cell_id=cell_id_for(forecast.latitude, forecast.longitude),
            value=forecast.value,
            unit=forecast.unit,
        )


class ForecastSource(ABC):
    """Contract future live-source adapters will implement unchanged."""

    source_id: str

    @abstractmethod
    def fetch_forecast(self, scenario: str, lead_hours: int) -> list[ForecastRecord]:
        """Return normalized canonical records without network access in demo mode."""


class _DemoScenarioSource(ForecastSource):
    def fetch_forecast(self, scenario: str, lead_hours: int) -> list[ForecastRecord]:
        return [
            ForecastRecord.from_forecast(forecast)
            for forecast in scenario_forecasts(scenario, lead_hours)
            if forecast.model_id == self.source_id
        ]


class DemoECMWFSource(_DemoScenarioSource):
    source_id = "ecmwf"


class DemoGFSSource(_DemoScenarioSource):
    source_id = "gfs"


class DemoGEFSSource(_DemoScenarioSource):
    source_id = "gefs"


class DemoAISource(_DemoScenarioSource):
    source_id = "ai"


DEMO_SOURCES: tuple[ForecastSource, ...] = (
    DemoECMWFSource(),
    DemoGFSSource(),
    DemoGEFSSource(),
    DemoAISource(),
)


def cell_id_for(latitude: float, longitude: float) -> str:
    return f"{latitude:.2f}:{longitude:.2f}"
