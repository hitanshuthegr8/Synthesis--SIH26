"""Historical model-skill metrics for model-comparison views."""
from fastapi import APIRouter, Query

from app.api.dependencies import demo_skills
from app.core.constants import SUPPORTED_VARIABLES
from app.domain.model import ModelSkill

router = APIRouter(tags=["model-analysis"])


@router.get("/api/model-analysis", response_model=list[ModelSkill])
def get_model_analysis(
    variable: str = Query("temperature"), lead_hours: int = Query(24, ge=0, le=168)
) -> list[ModelSkill]:
    if variable not in SUPPORTED_VARIABLES:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=f"Unsupported variable: {variable}")
    return demo_skills(variable, lead_hours)
