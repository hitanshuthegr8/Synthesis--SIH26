"""End-to-end: forecast cycle → verification → autopsy via public APIs."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.pipelines.forecast_cycle import cycle_registry


@pytest.mark.asyncio
async def test_generate_ingest_forecast_verify_autopsy_on_fresh_database() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = await client.post("/api/pipeline/run", json={"scenario": "heavy_rain", "lead_hours": 24})
        run_id = run.json()["run_id"]
        autopsy = await client.get(f"/api/autopsy/{run_id}")
        dossier = await client.get(f"/api/runs/{run_id}/dossier")

    assert run.status_code == 200
    assert autopsy.status_code == dossier.status_code == 200
    payload = run.json()
    assert payload["verification"]["absolute_error"] >= 0
    assert payload["autopsy"]["blend_error"] == pytest.approx(payload["verification"]["error"], rel=1e-6)
    restored = cycle_registry.get(run_id)
    assert restored is not None
    assert restored.autopsy.assessment
