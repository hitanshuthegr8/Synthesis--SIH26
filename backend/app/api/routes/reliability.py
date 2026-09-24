from fastapi import APIRouter, Query

from app.api.dependencies import demo_skills
from app.core.constants import SUPPORTED_VARIABLES
from app.skill.reliability import ReliabilityEngine, ReliabilityEstimate

router = APIRouter(prefix="/api/reliability", tags=["reliability"])


@router.get("/model", response_model=list[ReliabilityEstimate])
def get_reliability(variable: str = Query("temperature"), lead_hours: int = Query(24, ge=0)) -> list[ReliabilityEstimate]:
    if variable not in SUPPORTED_VARIABLES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Unsupported variable: {variable}")
    return ReliabilityEngine(minimum_samples=1).estimate(demo_skills(variable, lead_hours))
