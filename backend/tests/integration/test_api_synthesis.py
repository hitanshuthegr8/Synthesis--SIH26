from datetime import datetime, timezone

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import synthesis
from app.main import app
from app.spatial.forecast import SpatialForecastUnavailable


async def get(path: str, **params: object):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path, params=params)


@pytest.mark.asyncio
async def test_catalog_loads_offline_with_all_sources_listed() -> None:
    response = await get("/api/synthesis/catalog")
    assert response.status_code == 200
    payload = response.json()
    assert [source["id"] for source in payload["sources"]] == ["GFS", "ECMWF", "AIFS"]
    assert all(source["enabled"] is False for source in payload["sources"])
    assert {variable["id"] for variable in payload["variables"]} == {"temperature", "tmax", "precipitation", "wind_speed"}
    assert {hazard["id"] for hazard in payload["hazards"]} == {"heavy_rain", "heat", "high_wind"}


@pytest.mark.asyncio
async def test_field_reports_unavailable_when_providers_are_disabled() -> None:
    response = await get("/api/synthesis/field", variable="temperature", lead_hours=24, layer="blend",
                         initialization="2026-09-28T00:00:00Z")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "UNAVAILABLE"
    assert payload["values"] is None
    assert "disabled" in payload["reason"]


@pytest.mark.asyncio
async def test_field_rejects_unknown_variable_layer_and_source() -> None:
    assert (await get("/api/synthesis/field", variable="humidity")).status_code == 422
    assert (await get("/api/synthesis/field", layer="nonsense")).status_code == 422
    assert (await get("/api/synthesis/field", layer="weights", source="XYZ")).status_code == 422


@pytest.mark.asyncio
async def test_field_serialises_available_layers(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_layer(variable, lead_hours, initialization, name, weighting, source):
        return np.full((141, 141), 2.5), {"variable": variable, "lead_hours": lead_hours,
                                          "initialization": "2026-09-28T00:00:00Z", "layer": name, "model": "AIRAVAT"}

    monkeypatch.setattr(synthesis, "layer", fake_layer)
    response = await get("/api/synthesis/field", variable="wind_speed", lead_hours=48, layer="spread",
                         initialization="2026-09-28T00:00:00Z")
    payload = response.json()
    assert payload["status"] == "AVAILABLE"
    assert payload["units"] == "m/s"
    assert len(payload["values"]) == 141 and len(payload["latitudes"]) == 141
    assert payload["summary"]["india_mean"] == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_skill_and_extremes_surface_unavailability(monkeypatch: pytest.MonkeyPatch) -> None:
    response = await get("/api/synthesis/skill", variable="precipitation", lead_hours=24, initialization="2026-09-28T00:00:00Z")
    assert response.json()["status"] == "UNAVAILABLE"

    def unavailable(*_args, **_kwargs):
        raise SpatialForecastUnavailable("No 00Z cycle")

    monkeypatch.setattr(synthesis, "latest_cycle", unavailable)
    response = await get("/api/synthesis/extremes", day=1)
    assert response.json() == {"status": "UNAVAILABLE", "reason": "No 00Z cycle", "day": 1}


@pytest.mark.asyncio
async def test_operational_run_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    monkeypatch.setattr(synthesis.operations, "start_run", lambda run: started.append(run["run_id"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/synthesis/runs", json={
            "initialization": "2026-09-28T00:00:00Z", "variables": ["temperature"], "leads": [24], "days": [1]})
        assert response.status_code == 200
        run = response.json()
        assert run["status"] == "queued"
        assert run["total_steps"] == 2
        assert started == [run["run_id"]]
        assert (await client.get(f"/api/synthesis/runs/{run['run_id']}")).json()["run_id"] == run["run_id"]
        assert any(item["run_id"] == run["run_id"] for item in (await client.get("/api/synthesis/runs")).json())
        assert (await client.get("/api/synthesis/runs/unknown")).status_code == 404
        bad = await client.post("/api/synthesis/runs", json={"initialization": "2026-09-28T00:00:00Z", "variables": ["humidity"]})
        assert bad.status_code == 422


def test_operational_run_records_unavailable_steps_without_failing(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(synthesis.operations, "RUNS_DIR", tmp_path / "runs")
    run = synthesis.operations.create_run(datetime(2026, 9, 28, tzinfo=timezone.utc), ["temperature"], [24], [1])
    synthesis.operations.execute(run)
    assert run["status"] in {"complete", "complete_with_issues"}
    assert run["completed_steps"] == run["total_steps"]
    assert {entry["status"] for entry in run["log"]} <= {"unavailable", "warning", "complete"}
    synthesis.operations._runs.pop(run["run_id"])
    reloaded = synthesis.operations.get_run(run["run_id"])
    assert reloaded is not None and reloaded["status"] == run["status"]
    assert any(item["run_id"] == run["run_id"] for item in synthesis.operations.list_runs())
