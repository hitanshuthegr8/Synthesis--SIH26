"""Phase 1.5 orchestration and inspection API.

The existing focused endpoints remain available; these routes expose the
reproducible run-oriented contract used by the demonstration workflow.
"""
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import demo_forecasts, demo_observation, demo_skills
from app.api.routes.blend import build_demo_blend
from app.core.config import settings
from app.core.constants import SUPPORTED_VARIABLES
from app.domain.uncertainty import BlendResult
from app.verification.autopsy import ForecastAutopsyEngine

router = APIRouter(prefix="/api", tags=["phase-1.5"])
_runs: dict[str, dict] = {}


class PipelineRunRequest(BaseModel):
    variable: str = "temperature"
    lead_hours: int = Field(default=24, ge=0, le=384)
    scenario: str | None = None


class ScenarioRequest(PipelineRunRequest):
    scenario: str = "normal"


class ReplayRequest(BaseModel):
    run_id: str


def _validate(request: PipelineRunRequest) -> None:
    if request.variable not in SUPPORTED_VARIABLES:
        raise HTTPException(status_code=422, detail=f"Unsupported variable: {request.variable}")


def _run(request: PipelineRunRequest) -> dict:
    _validate(request)
    blend = build_demo_blend(request.variable, request.lead_hours, request.scenario)
    forecasts = demo_forecasts(request.variable, request.lead_hours, request.scenario)
    observation = demo_observation(request.variable, request.lead_hours, request.scenario)
    verification, _ = ForecastAutopsyEngine().analyze(blend, forecasts, observation)
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    config_hash = sha256(
        f"{settings.VERSION}|{settings.RANDOM_SEED}|{request.model_dump_json()}".encode()
    ).hexdigest()[:16]
    blend = blend.model_copy(update={
        "cycle_time": forecasts[0].initialization_time.isoformat().replace("+00:00", "Z"),
        "algorithm_version": settings.VERSION,
        "dataset_version": "demo-v1",
        "config_hash": config_hash,
        "source_availability": {item.model_id: "available" for item in forecasts},
    })
    trace = {
        "run_id": blend.run_id,
        "created_at": created_at,
        "stages": [
            {"name": "ingestion", "status": "complete", "record_count": len(forecasts)},
            {"name": "validation", "status": "complete", "record_count": len(forecasts)},
            {"name": "normalization", "status": "complete", "record_count": len(forecasts)},
            {"name": "regime", "status": "complete", "regime": blend.regime},
            {"name": "disagreement", "status": "complete", "level": blend.disagreement.level},
            {"name": "skill_and_weighting", "status": "complete"},
            {"name": "blend_and_uncertainty", "status": "complete"},
            {"name": "verification", "status": "complete"},
        ],
        "provenance": {
            "algorithm_version": blend.algorithm_version,
            "dataset_version": blend.dataset_version,
            "config_hash": blend.config_hash,
            "random_seed": settings.RANDOM_SEED,
            "demo_mode": settings.DEMO_MODE,
        },
    }
    _runs[blend.run_id] = {
        "run_id": blend.run_id,
        "blend": blend,
        "forecasts": forecasts,
        "verification": verification,
        "trace": trace,
        "request": request.model_dump(),
    }
    return _runs[blend.run_id]


@router.get("/sources")
def sources() -> list[dict[str, str]]:
    return [
        {"source": source, "status": "available", "mode": "synthetic_demo"}
        for source in ("ecmwf", "gfs", "gefs", "ai")
    ]


@router.post("/pipeline/run")
def run_pipeline(request: PipelineRunRequest) -> dict:
    return _run(request)


@router.get("/pipeline/{run_id}")
def pipeline_status(run_id: str) -> dict:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run["trace"]


@router.post("/forecast/analyze", response_model=BlendResult)
def analyze_forecast(request: PipelineRunRequest) -> BlendResult:
    return _run(request)["blend"]


@router.get("/forecast/{run_id}", response_model=BlendResult)
def get_forecast(run_id: str) -> BlendResult:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run["blend"]


@router.get("/computation/{run_id}")
def computation_trace(run_id: str) -> dict:
    return pipeline_status(run_id)


@router.get("/reliability")
def reliability(
    variable: str = Query("temperature"),
    lead_hours: int = Query(24, ge=0),
    scenario: str | None = None,
) -> list:
    _validate(PipelineRunRequest(variable=variable, lead_hours=lead_hours, scenario=scenario))
    return demo_skills(variable, lead_hours)


@router.get("/model-analysis")
def model_analysis(variable: str = Query("temperature"), lead_hours: int = Query(24, ge=0)) -> dict:
    skills = demo_skills(variable, lead_hours)
    return {
        "variable": variable,
        "lead_hours": lead_hours,
        "metrics": [
            {"model_id": skill.model_id, "mae": skill.score, "sample_count": skill.sample_count}
            for skill in skills
        ],
    }


@router.get("/autopsy/{run_id}")
def autopsy(run_id: str) -> dict:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run["verification"].model_dump(mode="json")


@router.post("/demo/scenario")
def demo_scenario(request: ScenarioRequest) -> dict:
    return _run(request)


@router.post("/demo/replay")
def replay(request: ReplayRequest) -> dict:
    run = _runs.get(request.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run(PipelineRunRequest(**run["request"]))


@router.get("/runs/{run_id}/dossier")
def dossier(run_id: str) -> dict:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run": run["blend"],
        "inputs": run["forecasts"],
        "verification": run["verification"],
        "computation_trace": run["trace"],
    }
