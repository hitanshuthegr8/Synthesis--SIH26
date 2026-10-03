"""Property-style invariants for weights and blending (Phase 1.5 hardening)."""
import random
from datetime import datetime, timezone

import pytest

from app.blending.engine import BlendEngine
from app.blending.weights import normalize_trust_scores
from app.core.constants import SUPPORTED_MODELS, VARIABLE_UNITS
from app.domain.forecast import Forecast


def _forecast(model_id: str, value: float, variable: str = "precipitation") -> Forecast:
    return Forecast(
        model_id=model_id,
        variable=variable,
        latitude=19.076,
        longitude=72.8777,
        initialization_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        lead_hours=24,
        value=value,
        unit=VARIABLE_UNITS[variable],
    )


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 99])
def test_normalized_weights_form_a_simplex(seed: int) -> None:
    random.seed(seed)
    raw = {model: random.uniform(0.01, 5.0) for model in SUPPORTED_MODELS}
    weights = normalize_trust_scores(raw)
    assert len(weights) == len(SUPPORTED_MODELS)
    assert all(weight >= 0 for weight in weights.values())
    assert sum(weights.values()) == pytest.approx(1.0)


@pytest.mark.parametrize("seed", range(20))
def test_blend_lies_between_source_min_and_max(seed: int) -> None:
    random.seed(seed + 1000)
    values = {model: random.uniform(0.0, 120.0) for model in SUPPORTED_MODELS}
    forecasts = [_forecast(model, value) for model, value in values.items()]
    weights = normalize_trust_scores({model: random.uniform(0.05, 3.0) for model in SUPPORTED_MODELS})
    blend = BlendEngine().blend(forecasts, weights)
    assert min(values.values()) <= blend.value <= max(values.values())


def test_identical_sources_yield_identical_blend() -> None:
    value = 44.3
    forecasts = [_forecast(model, value) for model in SUPPORTED_MODELS]
    weights = normalize_trust_scores({model: 1.0 for model in SUPPORTED_MODELS})
    blend = BlendEngine().blend(forecasts, weights)
    assert blend.value == pytest.approx(value)


def test_missing_source_renormalizes_without_crash() -> None:
    forecasts = [_forecast("ecmwf", 48.0), _forecast("gfs", 21.0), _forecast("ai", 57.0)]
    weights = normalize_trust_scores({"ecmwf": 0.4, "gfs": 0.2, "ai": 0.4})
    blend = BlendEngine().blend(forecasts, weights)
    assert sum(blend.weights.values()) == pytest.approx(1.0)
    assert set(blend.weights) == {"ecmwf", "gfs", "ai"}
