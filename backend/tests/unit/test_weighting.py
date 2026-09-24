"""TASKS 011-012 — Base and contextual weight calculation tests."""
import pytest

from app.blending.contextual import ContextualWeightAdjuster
from app.blending.weights import calculate_base_weights, normalize_trust_scores
from app.core.constants import DisagreementLevel
from app.domain.model import ModelSkill


def skill(model_id: str, score: float, metric: str = "mae") -> ModelSkill:
    return ModelSkill(
        model_id=model_id,
        variable="temperature",
        lead_hours=24,
        metric=metric,
        score=score,
        sample_count=100,
    )


def test_base_weights_are_inverse_error_and_normalized() -> None:
    weights = calculate_base_weights([skill("ecmwf", 1.0), skill("gfs", 2.0), skill("ai", 4.0)])

    assert weights == pytest.approx({"ecmwf": 4 / 7, "gfs": 2 / 7, "ai": 1 / 7})
    assert sum(weights.values()) == pytest.approx(1.0)


def test_base_weights_ignore_non_mae_records() -> None:
    weights = calculate_base_weights([skill("ecmwf", 1.0), skill("gfs", 10.0, metric="rmse")])

    assert weights == {"ecmwf": 1.0}


@pytest.mark.parametrize("scores", [{}, {"ecmwf": -1.0}])
def test_normalize_trust_scores_rejects_invalid_input(scores) -> None:
    with pytest.raises(ValueError):
        normalize_trust_scores(scores)


def test_contextual_regime_and_recent_skill_can_change_ranking() -> None:
    adjusted, details = ContextualWeightAdjuster().adjust(
        {"ecmwf": 0.6, "gfs": 0.4},
        base_mae={"ecmwf": 1.0, "gfs": 1.5},
        regime_mae={"ecmwf": 2.0, "gfs": 0.5},
        recent_mae={"ecmwf": 1.0, "gfs": 0.5},
    )

    assert adjusted["gfs"] > adjusted["ecmwf"]
    assert sum(adjusted.values()) == pytest.approx(1.0)
    assert next(item for item in details if item.model_id == "gfs").regime_factor == 1.5


def test_extreme_disagreement_pulls_weights_toward_equal() -> None:
    base = {"ecmwf": 0.9, "gfs": 0.1}
    adjusted, details = ContextualWeightAdjuster().adjust(
        base,
        base_mae={"ecmwf": 1.0, "gfs": 9.0},
        disagreement=DisagreementLevel.EXTREME,
    )

    assert 0.5 < adjusted["ecmwf"] < base["ecmwf"]
    assert adjusted["gfs"] > base["gfs"]
    assert all(item.disagreement_factor != 1.0 for item in details)


def test_contextual_adjuster_requires_matching_models() -> None:
    with pytest.raises(ValueError, match="same models"):
        ContextualWeightAdjuster().adjust({"ecmwf": 1.0}, base_mae={"gfs": 1.0})
