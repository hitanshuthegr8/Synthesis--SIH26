"""Demo-only scenario selection, provenance, and deterministic replay API."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.demo.generator import generate_demo_data, validate_demo_data
from app.api.routes.pipeline import PipelineRunRequest
from app.pipelines.forecast_cycle import ForecastCycleResult, NoUsableSourcesError, replay_forecast_cycle, run_forecast_cycle

router = APIRouter(prefix="/api/demo", tags=["demo"])


class ReplayRequest(BaseModel):
    run_id: str


class DemoManifestResponse(BaseModel):
    dataset_version: str
    generation_seed: int
    created_at: str
    scenario: str
    file_hashes: dict[str, str]
    integrity: str
    source_mode: str = "synthetic_benchmark"


@router.get("/manifest", response_model=DemoManifestResponse)
def get_demo_manifest() -> DemoManifestResponse:
    """Return a verified, reproducible manifest for the local benchmark archive."""
    archive_dir = Path(settings.DATA_DIR) / "demo"
    if not (archive_dir / "MANIFEST.json").exists():
        generate_demo_data(archive_dir, seed=settings.RANDOM_SEED)
    manifest = validate_demo_data(archive_dir)
    return DemoManifestResponse(**manifest, integrity="verified")


@router.post("/scenario", response_model=ForecastCycleResult)
def run_demo_scenario(request: PipelineRunRequest) -> ForecastCycleResult:
    try:
        return run_forecast_cycle(
            request.scenario,
            request.lead_hours,
            unavailable_sources=tuple(request.unavailable_sources),
            corrupt_sources=tuple(request.corrupt_sources),
        )
    except NoUsableSourcesError as error:
        raise HTTPException(status_code=503, detail={"error": {"code": "NO_USABLE_SOURCES", "message": str(error), "recoverable": True}}) from error


@router.post("/replay", response_model=ForecastCycleResult)
def replay_demo_run(request: ReplayRequest) -> ForecastCycleResult:
    try:
        return replay_forecast_cycle(request.run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "RUN_NOT_FOUND", "message": "Replay source run is not available", "run_id": request.run_id, "recoverable": False}}) from None
