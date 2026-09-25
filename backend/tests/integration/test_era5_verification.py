import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_verification_is_unavailable_when_era5_is_disabled() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/forecast/verification/spatial",
            params={"lead_hours": 24, "initialization": "2026-09-25T00:00:00Z"},
        )
    payload = response.json()
    assert payload["status"] == "UNAVAILABLE"
    assert "truth unavailable" in payload["reason"]
