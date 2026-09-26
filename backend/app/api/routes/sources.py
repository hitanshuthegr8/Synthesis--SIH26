"""Source-adapter availability API for the offline synthetic benchmark."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.ingestion.sources import DEMO_SOURCES

router = APIRouter(prefix="/api/sources", tags=["sources"])


class SourceHealth(BaseModel):
    source_id: str
    status: str
    mode: str
    message: str


@router.get("", response_model=list[SourceHealth])
def list_sources() -> list[SourceHealth]:
    return [
        SourceHealth(
            source_id=source.source_id,
            status="available",
            mode="synthetic_benchmark",
            message="Deterministic DEMO MODE adapter is available",
        )
        for source in DEMO_SOURCES
    ]
