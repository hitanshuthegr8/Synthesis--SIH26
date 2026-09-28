from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.config import settings
from app.spatial.forecast import GRID_SPEC, SpatialForecast, SpatialForecastUnavailable


@pytest.mark.asyncio
async def test_spatial_grid_reports_unavailable_without_values() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/forecast/grid", params={"variable": "temperature", "lead_hours": 168})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "UNAVAILABLE"
    assert payload["lead_hours"] == 168
    assert payload["grid_spec"]["resolution"] == 0.25
    assert payload["grid_spec"]["latitude_count"] == 141
    assert payload["grid_spec"]["longitude_count"] == 141
    assert payload["values"] is None
    assert "no GRIB" in payload["reason"]


@pytest.mark.asyncio
async def test_spatial_grid_exposes_validated_gfs_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    values = [[1.0 for _ in range(GRID_SPEC.longitude_count)] for _ in range(GRID_SPEC.latitude_count)]
    forecast = SpatialForecast(
        source="NOAA",
        variable="temperature",
        initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        lead_hours=24,
        units="C",
        grid=GRID_SPEC,
        latitudes=[GRID_SPEC.south + index * GRID_SPEC.resolution for index in range(GRID_SPEC.latitude_count)],
        longitudes=[GRID_SPEC.west + index * GRID_SPEC.resolution for index in range(GRID_SPEC.longitude_count)],
        values=values,
        provenance={
            "model": "GFS",
            "product": "gfs.t00z.pgrb2.0p25.f024",
            "source_units": "K",
            "normalized_units": "C",
            "target_resolution": 0.25,
            "target_domain": {"south": 5.0, "north": 40.0, "west": 65.0, "east": 100.0},
            "target_grid_transformation": "direct subset to target domain; no interpolation",
            "cache": {"hit": True},
        },
    )

    class MockProvider:
        def get_forecast(self, **_: object) -> SpatialForecast:
            return forecast

    monkeypatch.setattr(settings, "GFS_ENABLED", True)
    monkeypatch.setattr("app.api.routes.spatial.GFSProvider", MockProvider)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/forecast/grid",
            params={
                "source": "GFS",
                "model": "GFS",
                "variable": "temperature",
                "lead_hours": 24,
                "initialization": "2026-09-25T00:00:00Z",
            },
        )

    payload = response.json()
    assert payload["status"] == "AVAILABLE"
    assert payload["model"] == "GFS"
    assert payload["lead_hours"] == 24
    assert payload["units"] == "C"
    assert len(payload["latitudes"]) == 141
    assert len(payload["longitudes"]) == 141
    assert len(payload["values"]) == 141
    assert len(payload["values"][0]) == 141
    assert payload["provenance"]["product"] == "gfs.t00z.pgrb2.0p25.f024"
    assert payload["provenance"]["source_units"] == "K"
    assert payload["provenance"]["cache"]["hit"] is True


@pytest.mark.asyncio
async def test_spatial_grid_exposes_validated_ecmwf_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    values = [[2.0 for _ in range(GRID_SPEC.longitude_count)] for _ in range(GRID_SPEC.latitude_count)]
    forecast = SpatialForecast(
        source="ECMWF",
        variable="temperature",
        initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        lead_hours=24,
        units="C",
        grid=GRID_SPEC,
        latitudes=[GRID_SPEC.south + index * GRID_SPEC.resolution for index in range(GRID_SPEC.latitude_count)],
        longitudes=[GRID_SPEC.west + index * GRID_SPEC.resolution for index in range(GRID_SPEC.longitude_count)],
        values=values,
        provenance={
            "model": "IFS",
            "product": "20260925000000-24h-oper-fc.grib2",
            "source_units": "K",
            "normalized_units": "C",
            "parameter": "2t",
            "selected_byte_offset": 100,
            "selected_byte_length": 200,
            "target_grid_transformation": "direct subset to target domain; no interpolation",
        },
    )

    class MockProvider:
        def get_forecast(self, **_: object) -> SpatialForecast:
            return forecast

    monkeypatch.setattr(settings, "ECMWF_ENABLED", True)
    monkeypatch.setattr("app.api.routes.spatial.ECMWFProvider", MockProvider)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/forecast/grid",
            params={
                "source": "ECMWF",
                "model": "IFS",
                "variable": "temperature",
                "lead_hours": 24,
                "initialization": "2026-09-25T00:00:00Z",
            },
        )

    payload = response.json()
    assert payload["status"] == "AVAILABLE"
    assert payload["source"] == "ECMWF"
    assert payload["model"] == "IFS"
    assert payload["provenance"]["parameter"] == "2t"
    assert payload["provenance"]["selected_byte_offset"] == 100
    assert len(payload["values"]) == 141
    assert len(payload["values"][0]) == 141


@pytest.mark.asyncio
async def test_spatial_blend_endpoint_returns_unavailable_without_provider_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingService:
        def get_blended_forecast(self, **_: object) -> SpatialForecast:
            raise SpatialForecastUnavailable("ECMWF unavailable for requested lead")

    monkeypatch.setattr("app.api.routes.spatial.SpatialBlendService", FailingService)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/forecast/grid/blend",
            params={"lead_hours": 168, "initialization": "2026-09-25T00:00:00Z"},
        )
    payload = response.json()
    assert payload["status"] == "UNAVAILABLE"
    assert payload["source"] == "AIRAVAT"
    assert payload["values"] is None
    assert "ECMWF unavailable" in payload["reason"]
