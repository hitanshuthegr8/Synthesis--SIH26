"""Golden demo cycle regression — structural invariants, not brittle scalar targets."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_heavy_rain_cycle_001_completes_with_valid_outputs() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/pipeline/run", json={"scenario": "heavy_rain", "lead_hours": 24})

    assert response.status_code == 200
    payload = response.json()
    blend = payload["blend"]
    assert payload["status"] in {"complete", "degraded"}
    assert len(payload["forecasts"]) == 4
    assert blend["regime"] == "HEAVY_RAIN"
    assert blend["disagreement"]["level"] == "EXTREME"
    assert sum(blend["model_weights"].values()) == pytest.approx(1.0)
    assert all(weight >= 0 for weight in blend["model_weights"].values())
    assert blend["blended_value"] == pytest.approx(
        sum(
            forecast["value"] * blend["model_weights"][forecast["model_id"]]
            for forecast in payload["forecasts"]
        ),
        rel=1e-6,
    )
    assert blend["upper_bound"] >= blend["blended_value"] >= blend["lower_bound"]
    assert blend["explanation"]
    assert payload["trace"]["steps"]
