"""Phase 1.5 cycle, trace, replay, and failure-injection integration tests."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.pipelines.forecast_cycle import ForecastCycleRegistry, NoUsableSourcesError, run_forecast_cycle
from app.storage.database import SQLiteDatabase
from app.storage.repositories import SynthesisRepository


@pytest.mark.asyncio
async def test_pipeline_run_exposes_trace_and_all_cycle_steps() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = await client.post("/api/pipeline/run", json={"scenario": "heavy_rain", "lead_hours": 24})
        run_payload = run.json()
        trace = await client.get(f"/api/pipeline/computation/{run_payload['run_id']}")

    assert run.status_code == trace.status_code == 200
    assert run_payload["blend"]["regime"] == "HEAVY_RAIN"
    assert run_payload["blend"]["disagreement"]["level"] == "EXTREME"
    assert [step["name"] for step in trace.json()["steps"]] == [
        "source_ingestion", "validation_normalization", "historical_skill", "context", "adaptive_weighting", "blend_uncertainty", "verification_autopsy",
    ]
    assert trace.json()["output"]["processing_time_ms"] >= 0
    assert trace.json()["cycle_time"] == "2026-01-01T00:00:00Z"
    assert len(trace.json()["configuration_hash"]) == 64
    assert trace.json()["output"]["configuration_hash"] == trace.json()["configuration_hash"]


@pytest.mark.asyncio
async def test_replay_preserves_deterministic_scientific_outputs() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        original = await client.post("/api/demo/scenario", json={"scenario": "heavy_rain", "lead_hours": 24})
        replay = await client.post("/api/demo/replay", json={"run_id": original.json()["run_id"]})

    assert original.status_code == replay.status_code == 200
    assert replay.json()["blend"]["model_weights"] == original.json()["blend"]["model_weights"]
    assert replay.json()["blend"]["blended_value"] == original.json()["blend"]["blended_value"]
    assert replay.json()["blend"]["lower_bound"] == original.json()["blend"]["lower_bound"]


@pytest.mark.asyncio
async def test_model_disagreement_alias_matches_model_conflict() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        alias = await client.post("/api/pipeline/run", json={"scenario": "model_disagreement", "lead_hours": 24})
        canonical = await client.post("/api/pipeline/run", json={"scenario": "model_conflict", "lead_hours": 24})

    assert alias.status_code == canonical.status_code == 200
    assert alias.json()["blend"]["disagreement"]["level"] == canonical.json()["blend"]["disagreement"]["level"]


@pytest.mark.asyncio
async def test_model_failure_penalizes_gfs_and_renormalizes_weights() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        heavy_rain = await client.post("/api/demo/scenario", json={"scenario": "heavy_rain", "lead_hours": 24})
        failure = await client.post("/api/demo/scenario", json={"scenario": "model_failure", "lead_hours": 24})

    heavy_weights = heavy_rain.json()["blend"]["model_weights"]
    failure_payload = failure.json()
    failure_weights = failure_payload["blend"]["model_weights"]
    assert failure.status_code == 200
    assert failure_weights["gfs"] < heavy_weights["gfs"]
    assert sum(failure_weights.values()) == pytest.approx(1.0)
    assert any("GFS source flagged" in detail for detail in failure_payload["trace"]["steps"][4]["details"])


@pytest.mark.asyncio
async def test_public_phase15_routes_retrieve_the_same_auditable_run() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cycle = await client.post("/api/pipeline/run", json={"scenario": "normal", "lead_hours": 48})
        run_id = cycle.json()["run_id"]
        trace = await client.get(f"/api/computation/{run_id}")
        forecast = await client.get(f"/api/forecast/{run_id}")
        dossier = await client.get(f"/api/runs/{run_id}/dossier")
        model_analysis = await client.get("/api/model-analysis", params={"variable": "temperature", "lead_hours": 24})
        grid = await client.get("/api/grid/reliability", params={"variable": "precipitation", "lead_hours": 24})
        system_status = await client.get("/api/system/status")

    assert trace.status_code == forecast.status_code == dossier.status_code == model_analysis.status_code == grid.status_code == system_status.status_code == 200
    assert trace.json()["run_id"] == dossier.json()["run_id"] == run_id
    assert forecast.json()["run_id"] == run_id
    assert {item["metric"] for item in model_analysis.json()} == {"mae", "rmse", "bias"}
    assert grid.json()["latitude_count"] == grid.json()["longitude_count"] == 141
    assert len(grid.json()["points"]) == 141 * 141
    assert grid.json()["resolution_degrees"] == 0.25
    assert {source["source_id"] for source in system_status.json()["source_adapters"]} == {"ecmwf", "gfs", "gefs", "ai"}
    assert system_status.json()["last_cycle_run_id"] == run_id


def test_forecast_cycle_can_be_restored_from_sqlite_after_cache_reset(tmp_path) -> None:
    repository = SynthesisRepository(SQLiteDatabase(tmp_path / "cycles.db"))
    original_registry = ForecastCycleRegistry(repository)
    result = run_forecast_cycle("normal", registry=original_registry)

    restarted_registry = ForecastCycleRegistry(repository)
    restored = restarted_registry.get(result.run_id)

    assert restored is not None
    assert restored.blend.model_dump(mode="json") == result.blend.model_dump(mode="json")
    assert [step.model_dump() for step in restored.trace.steps] == [step.model_dump() for step in result.trace.steps]


@pytest.mark.asyncio
async def test_missing_and_corrupt_sources_are_explicitly_degraded() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        complete = await client.post("/api/pipeline/run", json={"scenario": "normal"})
        degraded = await client.post("/api/pipeline/run", json={"scenario": "normal", "unavailable_sources": ["gfs"]})
        fallback = await client.post("/api/pipeline/run", json={"scenario": "normal", "corrupt_sources": ["gfs", "gefs", "ai"]})
        stale = await client.post("/api/pipeline/run", json={"scenario": "normal", "unavailable_sources": ["ecmwf", "gfs", "gefs", "ai"]})

    assert degraded.status_code == fallback.status_code == 200
    assert degraded.json()["status"] == "degraded"
    assert degraded.json()["trace"]["source_availability"]["gfs"] is False
    assert degraded.json()["blend"]["upper_bound"] - degraded.json()["blend"]["lower_bound"] > complete.json()["blend"]["upper_bound"] - complete.json()["blend"]["lower_bound"]
    assert fallback.json()["blend"]["fallback_mode"] is True
    assert any("SINGLE SOURCE FALLBACK" in line for line in fallback.json()["blend"]["explanation"])
    assert stale.status_code == 200
    assert stale.json()["status"] == "stale"
    assert stale.json()["trace"]["stale_from_run_id"] is not None
    assert any("STALE:" in line for line in stale.json()["blend"]["explanation"])


def test_all_source_loss_without_a_last_good_forecast_is_recoverable() -> None:
    repository = SynthesisRepository(SQLiteDatabase(":memory:"))
    with pytest.raises(NoUsableSourcesError, match="No usable source forecasts"):
        run_forecast_cycle(
            "normal",
            registry=ForecastCycleRegistry(repository),
            unavailable_sources=("ecmwf", "gfs", "gefs", "ai"),
        )
