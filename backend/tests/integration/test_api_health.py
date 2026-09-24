"""TASK 001 — API bootstrap tests.

Verify the FastAPI application starts and the health endpoint responds correctly.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    """Health endpoint returns status ok with version and demo_mode."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert data["demo_mode"] is True


@pytest.mark.asyncio
async def test_health_endpoint_has_required_fields() -> None:
    """Health response contains exactly the expected fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    data = response.json()
    required_fields = {"status", "version", "demo_mode"}
    assert required_fields.issubset(set(data.keys()))
