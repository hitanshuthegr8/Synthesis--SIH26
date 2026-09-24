"""Isolated, interpretable conversion from historical error to model weights."""
from collections.abc import Mapping, Sequence

from app.core.constants import EPSILON
from app.domain.model import ModelSkill


def calculate_base_weights(skills: Sequence[ModelSkill]) -> dict[str, float]:
    """Convert MAE records into normalized inverse-error weights.

    Only one MAE record per model may be supplied for one forecast context.
    This narrow interface lets a later empirical-Bayes estimator replace the
    weighting logic without changing the blend engine.
    """
    mae_by_model: dict[str, float] = {}
    for skill in skills:
        if skill.metric != "mae":
            continue
        if skill.score < 0.0:
            raise ValueError("MAE scores must be non-negative")
        if skill.model_id in mae_by_model:
            raise ValueError(f"More than one MAE score provided for '{skill.model_id}'")
        mae_by_model[skill.model_id] = skill.score
    return normalize_trust_scores({model_id: 1.0 / max(mae, EPSILON) for model_id, mae in mae_by_model.items()})


def normalize_trust_scores(scores: Mapping[str, float]) -> dict[str, float]:
    """Normalize positive trust scores while guarding against empty or invalid input."""
    if not scores:
        raise ValueError("At least one model trust score is required")
    if any(score < 0.0 for score in scores.values()):
        raise ValueError("Trust scores cannot be negative")
    total = sum(scores.values())
    if total <= EPSILON:
        uniform_weight = 1.0 / len(scores)
        return {model_id: uniform_weight for model_id in scores}
    return {model_id: score / total for model_id, score in scores.items()}
