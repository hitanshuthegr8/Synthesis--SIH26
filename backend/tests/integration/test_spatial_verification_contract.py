from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.spatial.forecast import GRID_SPEC, SpatialForecastUnavailable
from app.spatial.verification import SpatialTruth


def _axes() -> tuple[list[float], list[float]]:
    return (
        [5.0 + index * 0.25 for index in range(141)],
        [65.0 + index * 0.25 for index in range(141)],
    )


def _forecast() -> object:
    from app.spatial.forecast import SpatialForecast

    latitudes, longitudes = _axes()
    return SpatialForecast(
        source="GFS",
        variable="temperature",
        initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        lead_hours=24,
        units="C",
        grid=GRID_SPEC,
        latitudes=latitudes,
        longitudes=longitudes,
        values=[[10.0] * 141 for _ in range(141)],
        provenance={"model": "GFS"},
    )


def _truth() -> SpatialTruth:
    forecast = _forecast()
    return SpatialTruth(
        source="ERA5",
        variable=forecast.variable,
        initialization=forecast.initialization,
        lead_hours=forecast.lead_hours,
        units=forecast.units,
        grid=forecast.grid,
        latitudes=forecast.latitudes,
        longitudes=forecast.longitudes,
        values=[[8.0] * 141 for _ in range(141)],
        provenance={"dataset": "reanalysis-era5-single-levels"},
    )


@pytest.mark.asyncio
async def test_spatial_verification_route_returns_metrics_and_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    class ForecastProvider:
        def get_forecast(self, **_kwargs: object) -> object:
            return _forecast()

    class TruthProvider:
        def get_truth(self, **_kwargs: object) -> SpatialTruth:
            return _truth()

    monkeypatch.setattr(settings, "ERA5_ENABLED", True)
    monkeypatch.setattr(settings, "GFS_ENABLED", True)
    monkeypatch.setattr("app.api.routes.spatial.GFSProvider", ForecastProvider)
    monkeypatch.setattr("app.api.routes.spatial.ERA5Provider", TruthProvider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/forecast/verification/spatial",
            params={"source": "GFS", "model": "GFS", "initialization": "2026-09-25T00:00:00Z"},
        )
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "AVAILABLE"
    assert payload["metrics"]["mae"] == 2
    assert payload["metrics"]["rmse"] == 2
    assert payload["metrics"]["bias"] == 2
    assert payload["provenance"]["truth_source"] == "ERA5"
    assert payload["provenance"]["valid_time"] == "2026-09-26T00:00:00Z"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"source": "UNKNOWN", "model": "UNKNOWN"}, "Unsupported forecast source/model"),
        ({"initialization": "not-a-time"}, "Input should be a valid datetime"),
    ],
)
async def test_spatial_verification_route_rejects_invalid_requests(
    params: dict[str, str], reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ERA5_ENABLED", True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/forecast/verification/spatial", params=params)
    if response.status_code == 422:
        assert reason in response.text
    else:
        assert response.json()["status"] == "UNAVAILABLE"
        assert reason in response.json()["reason"]


@pytest.mark.asyncio
async def test_spatial_verification_route_keeps_forecast_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingProvider:
        def get_forecast(self, **_kwargs: object) -> object:
            raise SpatialForecastUnavailable("forecast unavailable")

    monkeypatch.setattr(settings, "ERA5_ENABLED", True)
    monkeypatch.setattr(settings, "GFS_ENABLED", True)
    monkeypatch.setattr("app.api.routes.spatial.GFSProvider", FailingProvider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/forecast/verification/spatial",
            params={"initialization": "2026-09-25T00:00:00Z"},
        )
    payload = response.json()
    assert payload["status"] == "UNAVAILABLE"
    assert payload["metrics"] is None
    assert "forecast unavailable" in payload["reason"]
