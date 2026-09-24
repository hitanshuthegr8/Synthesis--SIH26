from fastapi import APIRouter, Query

from app.api.dependencies import demo_forecasts
from app.core.constants import SUPPORTED_VARIABLES
from app.domain.forecast import Forecast

router = APIRouter(prefix="/api/forecasts", tags=["forecasts"])


@router.get("", response_model=list[Forecast])
def get_forecasts(variable: str = Query("temperature"), lead_hours: int = Query(24, ge=0), scenario: str | None = Query(default=None)) -> list[Forecast]:
    if variable not in SUPPORTED_VARIABLES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Unsupported variable: {variable}")
    return demo_forecasts(variable, lead_hours, scenario)
