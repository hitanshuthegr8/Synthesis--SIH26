"""Canonical 0.25-degree Phase 1.5 geographic reliability grid."""
import math

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.dependencies import demo_skills
from app.core.constants import SUPPORTED_VARIABLES

router = APIRouter(prefix="/api/grid", tags=["grid"])

LATITUDES = tuple(round(5.0 + index * 0.25, 2) for index in range(141))
LONGITUDES = tuple(round(65.0 + index * 0.25, 2) for index in range(141))


class ReliabilityGrid(BaseModel):
    """Backend-computed synthetic reliability surface on the canonical grid."""

    variable: str
    lead_hours: int
    metric: str
    dataset_version: str = "phase-1.5-demo-v1"
    mode: str = "synthetic_benchmark"
    latitude_count: int = 141
    longitude_count: int = 141
    resolution_degrees: float = 0.25
    latitudes: list[float]
    longitudes: list[float]
    points: list[tuple[int, int, float]] = Field(description="[longitude index, latitude index, reliability]")
    india_focus: dict[str, float] = Field(description="Approximate India focus extent within the canonical domain")


@router.get("/reliability", response_model=ReliabilityGrid)
def get_reliability_grid(
    variable: str = Query("precipitation"), lead_hours: int = Query(24, ge=24, le=168)
) -> ReliabilityGrid:
    if variable not in SUPPORTED_VARIABLES:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=f"Unsupported variable: {variable}")

    mae_records = [item for item in demo_skills(variable, lead_hours) if item.metric == "mae"]
    mean_mae = sum(item.score for item in mae_records) / len(mae_records)
    lead_penalty = (lead_hours - 24) / 1440
    points = [
        (longitude_index, latitude_index, _reliability_value(latitude, longitude, mean_mae, lead_penalty))
        for latitude_index, latitude in enumerate(LATITUDES)
        for longitude_index, longitude in enumerate(LONGITUDES)
    ]
    return ReliabilityGrid(
        variable=variable,
        lead_hours=lead_hours,
        metric="synthetic_reliability_index",
        latitudes=list(LATITUDES),
        longitudes=list(LONGITUDES),
        points=points,
        india_focus={"min_lat": 8.0, "max_lat": 37.0, "min_lon": 68.0, "max_lon": 97.0},
    )


def _reliability_value(latitude: float, longitude: float, mean_mae: float, lead_penalty: float) -> float:
    """Deterministic spatial variation anchored to computed historical MAE."""
    spatial_signal = 0.09 * math.sin(math.radians(latitude * 3.0)) + 0.07 * math.cos(math.radians(longitude * 2.0))
    india_focus = 0.05 * math.exp(-(((latitude - 22.5) / 12.0) ** 2 + ((longitude - 80.0) / 14.0) ** 2))
    mae_component = 1.0 / (1.0 + mean_mae)
    return round(max(0.0, min(1.0, mae_component + spatial_signal + india_focus - lead_penalty)), 4)
