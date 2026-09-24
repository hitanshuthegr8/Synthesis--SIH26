"""TASKS 020-024 — Demo API integration tests."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_forecasts_endpoint_returns_all_demo_models() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/forecasts", params={"variable": "temperature", "lead_hours": 24})

    assert response.status_code == 200
    assert {item["model_id"] for item in response.json()} == {"ecmwf", "gfs", "ai", "gefs"}


@pytest.mark.asyncio
async def test_blend_endpoint_returns_valid_weighted_result() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/blend", json={"variable": "precipitation", "lead_hours": 24})

    assert response.status_code == 200
    payload = response.json()
    assert payload["variable"] == "precipitation"
    assert sum(payload["model_weights"].values()) == pytest.approx(1.0)
    assert payload["upper_bound"] >= payload["lower_bound"]


@pytest.mark.asyncio
async def test_reliability_endpoint_exposes_sample_counts() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/reliability/model")

    assert response.status_code == 200
    assert len(response.json()) == 4
    assert all(item["sample_count"] == 5 for item in response.json())


@pytest.mark.asyncio
async def test_verification_endpoint_returns_error_details() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/verification", params={"variable": "wind_speed"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["absolute_error"] >= 0
    assert set(payload["model_errors"]) == {"ecmwf", "gfs", "ai", "gefs"}


@pytest.mark.asyncio
async def test_heavy_rain_demo_scenario_runs_end_to_end() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        forecasts = await client.get("/api/forecasts", params={"variable": "precipitation", "scenario": "heavy_rain"})
        blend = await client.post("/api/blend", json={"variable": "precipitation", "lead_hours": 24, "scenario": "heavy_rain"})
        verification = await client.get("/api/verification", params={"variable": "precipitation", "scenario": "heavy_rain"})

    assert forecasts.status_code == blend.status_code == verification.status_code == 200
    assert [item["value"] for item in forecasts.json()] == [48.0, 21.0, 57.0, 29.0]
    assert blend.json()["regime"] == "HEAVY_RAIN"
    assert blend.json()["disagreement"]["level"] in {"HIGH", "EXTREME"}
    assert verification.json()["observation_value"] == 52.0
