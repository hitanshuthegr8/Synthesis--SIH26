from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import demo_skills
from app.api.routes.grid import ReliabilityGrid, get_reliability_grid
from app.core.constants import SUPPORTED_MODELS, SUPPORTED_VARIABLES
from app.skill.reliability import ReliabilityEngine, ReliabilityEstimate

router = APIRouter(prefix="/api/reliability", tags=["reliability"])


class ReliabilityCell(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    latitude: float
    longitude: float
    model: str
    skill: float
    sample_count: int


class ReliabilityMapResponse(BaseModel):
    variable: str
    lead_hours: int
    season: Optional[str] = None
    regime: Optional[str] = None
    cells: list[ReliabilityCell] = Field(default_factory=list)


@router.get("/model", response_model=list[ReliabilityEstimate])
def get_reliability(
    variable: str = Query("temperature"),
    lead_hours: int = Query(24, ge=0),
) -> list[ReliabilityEstimate]:
    if variable not in SUPPORTED_VARIABLES:
        raise HTTPException(status_code=422, detail=f"Unsupported variable: {variable}")
    return ReliabilityEngine(minimum_samples=1).estimate(demo_skills(variable, lead_hours))


@router.get("", response_model=list[ReliabilityEstimate])
def get_reliability_summary(
    variable: str = Query("temperature"),
    lead_hours: int = Query(24, ge=0),
) -> list[ReliabilityEstimate]:
    return get_reliability(variable, lead_hours)


@router.get("/map", response_model=ReliabilityMapResponse)
def get_reliability_map(
    variable: str = Query("precipitation"),
    lead_hours: int = Query(24, ge=0),
    season: Optional[str] = Query(None),
    regime: Optional[str] = Query(None),
) -> ReliabilityMapResponse:
    """Return spatial model reliability cells across the region.

    Allows assessing spatial variation of which forecast model has superior
    historical skill across geographic cells.
    """
    if variable not in SUPPORTED_VARIABLES:
        raise HTTPException(status_code=422, detail=f"Unsupported variable: {variable}")

    skills = demo_skills(variable, lead_hours)
    mae_by_model = {item.model_id: item.score for item in skills if item.metric == "mae"}

    # Generate a canonical spatial grid covering Western India / Maharashtra (17N-22N, 72E-77E, 1.0 deg steps)
    cells: list[ReliabilityCell] = []
    lats = [17.0, 18.0, 19.0, 20.0, 21.0, 22.0]
    lons = [72.0, 73.0, 74.0, 75.0, 76.0, 77.0]

    for lat in lats:
        for lon in lons:
            # Deterministic spatial skill variation based on coastal vs inland and model bias
            for model_id in SUPPORTED_MODELS:
                base_mae = mae_by_model.get(model_id, 2.5)
                # Coastal adjustment (coastal cells near lon 72-73)
                coastal_adj = 0.85 if lon <= 73.0 and model_id in {"ecmwf", "ai"} else 1.0
                lead_decay = 1.0 + (lead_hours / 168.0) * 0.3
                eff_mae = base_mae * coastal_adj * lead_decay
                skill = round(1.0 / (1.0 + eff_mae), 3)
                sample_count = int(900 + (lat * 10) + (lon * 5))

                cells.append(
                    ReliabilityCell(
                        latitude=lat,
                        longitude=lon,
                        model=model_id,
                        skill=skill,
                        sample_count=sample_count,
                    )
                )

    return ReliabilityMapResponse(
        variable=variable,
        lead_hours=lead_hours,
        season=season,
        regime=regime,
        cells=cells,
    )


@router.get("/map/canonical", response_model=ReliabilityGrid)
def get_canonical_reliability_map(
    variable: str = Query("precipitation"), lead_hours: int = Query(24, ge=24, le=168)
) -> ReliabilityGrid:
    """Expose the full canonical grid through the established reliability API."""
    return get_reliability_grid(variable, lead_hours)
