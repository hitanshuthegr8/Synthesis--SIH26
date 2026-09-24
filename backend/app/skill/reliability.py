"""Sample-aware conversion of historical skill into interpretable model weights."""
from collections import defaultdict
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.constants import EPSILON
from app.domain.model import ModelSkill


class ReliabilityEstimate(BaseModel):
    model_id: str
    variable: str
    lead_hours: int = Field(ge=0)
    mae: float = Field(ge=0.0)
    sample_count: int = Field(ge=0)
    reliability: float = Field(ge=0.0, le=1.0)
    sufficient_samples: bool


class ReliabilityEngine:
    """Use inverse MAE weights only when each participating model has enough data."""

    def __init__(self, minimum_samples: int = settings.MINIMUM_SAMPLES) -> None:
        if minimum_samples <= 0:
            raise ValueError("minimum_samples must be positive")
        self.minimum_samples = minimum_samples

    def estimate(self, skills: list[ModelSkill]) -> list[ReliabilityEstimate]:
        grouped: dict[tuple[str, int], list[ModelSkill]] = defaultdict(list)
        for skill in skills:
            if skill.metric == "mae":
                grouped[(skill.variable, skill.lead_hours)].append(skill)

        estimates: list[ReliabilityEstimate] = []
        for (variable, lead_hours), group in sorted(grouped.items()):
            eligible = [skill for skill in group if skill.sample_count >= self.minimum_samples]
            inverse_total = sum(1.0 / max(skill.score, EPSILON) for skill in eligible)
            for skill in sorted(group, key=lambda item: item.model_id):
                sufficient = skill in eligible
                reliability = (1.0 / max(skill.score, EPSILON)) / inverse_total if sufficient else 0.0
                estimates.append(
                    ReliabilityEstimate(
                        model_id=skill.model_id,
                        variable=variable,
                        lead_hours=lead_hours,
                        mae=skill.score,
                        sample_count=skill.sample_count,
                        reliability=reliability,
                        sufficient_samples=sufficient,
                    )
                )
        return estimates
