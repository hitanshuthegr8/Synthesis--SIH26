from datetime import timedelta
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import demo_forecasts, demo_skills
from app.blending.engine import BlendEngine
from app.blending.explanation import ExplanationEngine
from app.blending.weights import calculate_base_weights
from app.core.constants import SUPPORTED_VARIABLES
from app.domain.uncertainty import BlendResult
from app.regime.classifier import RuleBasedRegimeClassifier
from app.uncertainty.disagreement import DisagreementEngine
from app.uncertainty.engine import UncertaintyEngine

router = APIRouter(prefix="/api/blend", tags=["blend"])


class BlendRequest(BaseModel):
    variable: str = "temperature"
    lead_hours: int = Field(default=24, ge=0)
    scenario: str | None = None


def build_demo_blend(variable: str, lead_hours: int, scenario: str | None = None) -> BlendResult:
    if variable not in SUPPORTED_VARIABLES:
        raise HTTPException(status_code=422, detail=f"Unsupported variable: {variable}")
    forecasts = demo_forecasts(variable, lead_hours, scenario)
    skills = [item for item in demo_skills(variable, lead_hours) if item.metric == "mae"]
    core = BlendEngine().blend(forecasts, calculate_base_weights(skills))
    disagreement = DisagreementEngine().calculate(forecasts)
    regime = RuleBasedRegimeClassifier().classify(forecasts)
    mae = sum(item.score for item in skills) / len(skills)
    uncertainty = UncertaintyEngine().estimate(core.value, disagreement, historical_mae=mae)
    return BlendResult(
        variable=variable, latitude=forecasts[0].latitude, longitude=forecasts[0].longitude,
        valid_time=(forecasts[0].initialization_time + timedelta(hours=lead_hours)).isoformat().replace('+00:00', 'Z'),
        blended_value=core.value, lower_bound=uncertainty.lower_bound, upper_bound=uncertainty.upper_bound,
        model_weights=core.weights, disagreement=disagreement, regime=regime.name.value,
        regime_confidence=regime.confidence,
        explanation=ExplanationEngine().generate(core.weights, regime, disagreement, uncertainty),
        fallback_mode=core.fallback_mode, run_id=f"demo-{uuid4().hex}",
    )


@router.post("", response_model=BlendResult)
def create_blend(request: BlendRequest) -> BlendResult:
    return build_demo_blend(request.variable, request.lead_hours, request.scenario)
