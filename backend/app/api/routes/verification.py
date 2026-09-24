from fastapi import APIRouter, Query

from app.api.dependencies import demo_forecasts, demo_observation
from app.api.routes.blend import build_demo_blend
from app.core.constants import SUPPORTED_VARIABLES
from app.domain.verification import VerificationResult
from app.verification.autopsy import ForecastAutopsyEngine

router = APIRouter(prefix="/api/verification", tags=["verification"])


@router.get("", response_model=VerificationResult)
def get_verification(variable: str = Query("temperature"), lead_hours: int = Query(24, ge=0), scenario: str | None = Query(default=None)) -> VerificationResult:
    if variable not in SUPPORTED_VARIABLES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Unsupported variable: {variable}")
    blend = build_demo_blend(variable, lead_hours, scenario)
    verification, _ = ForecastAutopsyEngine().analyze(blend, demo_forecasts(variable, lead_hours, scenario), demo_observation(variable, lead_hours, scenario))
    return verification
