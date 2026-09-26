"""Operational status for the self-contained Phase 1.5 deployment."""
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.routes.sources import SourceHealth, list_sources
from app.core.config import settings
from app.pipelines.forecast_cycle import cycle_registry

router = APIRouter(prefix="/api/system", tags=["system"])


class SystemStatus(BaseModel):
    api: str
    database: str
    pipeline: str
    demo_mode: bool
    source_adapters: list[SourceHealth]
    last_cycle_run_id: str | None
    last_successful_cycle: datetime | None
    last_processing_time_ms: int | None


@router.get("/status", response_model=SystemStatus)
def get_system_status() -> SystemStatus:
    try:
        latest = cycle_registry.latest()
        database = "available"
    except Exception:
        latest = None
        database = "unavailable"
    return SystemStatus(
        api="available",
        database=database,
        pipeline="ready" if database == "available" else "degraded",
        demo_mode=settings.DEMO_MODE,
        source_adapters=list_sources(),
        last_cycle_run_id=latest.run_id if latest else None,
        last_successful_cycle=latest.trace.created_at if latest else None,
        last_processing_time_ms=latest.trace.duration_ms if latest else None,
    )
