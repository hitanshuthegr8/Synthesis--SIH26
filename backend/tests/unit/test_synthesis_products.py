from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from app.spatial import products
from app.spatial.forecast import GRID_SPEC, SpatialForecast, SpatialForecastUnavailable

INIT = datetime(2026, 9, 28, tzinfo=timezone.utc)
SHAPE = (GRID_SPEC.latitude_count, GRID_SPEC.longitude_count)


class FakeProvider:
    """Deterministic provider: value = offset + lead/100, with per-variable/lead overrides."""

    def __init__(self, offset: float, missing_days: set[datetime] | None = None, overrides: dict | None = None) -> None:
        self.offset = offset
        self.missing_days = missing_days or set()
        self.overrides = overrides or {}
        self.calls: list[tuple] = []

    def get_forecast(self, *, variable: str, lead_hours: int, initialization: datetime) -> SpatialForecast:
        self.calls.append((variable, lead_hours, initialization))
        if initialization in self.missing_days:
            raise SpatialForecastUnavailable("gone from archive")
        value = self.overrides.get((variable, lead_hours), self.offset + lead_hours / 100)
        return SpatialForecast(
            source="FAKE", variable=variable, initialization=initialization, lead_hours=lead_hours, units="x",
            grid=GRID_SPEC, latitudes=products.LATITUDES.tolist(), longitudes=products.LONGITUDES.tolist(),
            values=np.full(SHAPE, value).tolist(),
        )


@pytest.fixture(autouse=True)
def isolated_skill_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(products, "SKILL_DIR", tmp_path / "skill")
    monkeypatch.setattr(products, "_skill_cache", {})


def test_india_mask_and_regions_cover_india_only() -> None:
    mask = products.india_mask()
    assert mask.shape == SHAPE
    assert 3000 < mask.sum() < 6000
    row, column = int((28.6 - GRID_SPEC.south) / 0.25), int((77.2 - GRID_SPEC.west) / 0.25)  # New Delhi
    assert mask[row, column]
    assert not mask[int((15 - GRID_SPEC.south) / 0.25), int((65 - GRID_SPEC.west) / 0.25)]  # Arabian Sea
    regions = products.region_masks()
    assert sum(region.sum() for region in regions.values()) == mask.sum()


def test_rainfall_is_the_24h_window_ending_at_valid_time() -> None:
    provider = FakeProvider(0, overrides={("precipitation", 48): 30.0, ("precipitation", 24): 12.0})
    store = products.FieldStore({"GFS": provider})
    assert store.field("GFS", "precipitation", 48, INIT)[0, 0] == pytest.approx(18.0)
    assert store.field("GFS", "precipitation", 24, INIT)[0, 0] == pytest.approx(12.0)


def test_ecmwf_tmax_combines_two_three_hour_maxima() -> None:
    provider = FakeProvider(0, overrides={("tmax", 33): 41.0, ("tmax", 36): 39.0})
    store = products.FieldStore({"ECMWF": provider})
    assert store.field("ECMWF", "tmax", 36, INIT)[0, 0] == pytest.approx(41.0)
    with pytest.raises(SpatialForecastUnavailable, match="AIFS"):
        products.FieldStore({"AIFS": provider}).field("AIFS", "tmax", 36, INIT)


def test_fields_reports_missing_sources_and_fails_when_none() -> None:
    store = products.FieldStore({"GFS": FakeProvider(1), "ECMWF": FakeProvider(2, missing_days={INIT})})
    available, missing = store.fields("temperature", 24, INIT)
    assert set(available) == {"GFS"}
    assert "gone from archive" in missing["ECMWF"]
    with pytest.raises(SpatialForecastUnavailable, match="No forecast source"):
        products.FieldStore({"ECMWF": FakeProvider(2, missing_days={INIT})}).fields("temperature", 24, INIT)


def skill_store(missing_ecmwf: set[datetime] | None = None) -> products.FieldStore:
    # Analyses (lead 0) are 0 for both; GFS forecasts miss by +1, IFS by +3, AIFS by -2.
    return products.FieldStore({
        "GFS": FakeProvider(0, overrides={("temperature", 24): 1.0, ("temperature", 0): 0.0}),
        "ECMWF": FakeProvider(0, missing_days=missing_ecmwf, overrides={("temperature", 24): 3.0, ("temperature", 0): 0.0}),
        "AIFS": FakeProvider(0, overrides={("temperature", 24): -2.0}),
    })


def test_skill_weights_favour_the_smaller_error_and_sum_to_one() -> None:
    result = products.compute_skill("temperature", 24, INIT, window_days=4, store=skill_store())
    assert result.sources == ["GFS", "ECMWF", "AIFS"]
    assert len(result.samples) == 4
    total = sum(result.weights.values())
    assert np.allclose(total, 1.0)
    assert result.weights["GFS"].mean() > result.weights["AIFS"].mean() > result.weights["ECMWF"].mean()
    # Constant biases are learnable, so bias correction must beat the equal-weight blend.
    assert result.evaluation["mae"]["adaptive"] < result.evaluation["mae"]["equal"]
    assert result.evaluation["method"] == "leave-one-out"
    assert set(result.evaluation["by_reference"]) == {"mean", "GFS", "ECMWF"}


def test_skill_skips_days_missing_a_model_and_persists(tmp_path: Path) -> None:
    missing = {INIT - timedelta(days=3), INIT - timedelta(days=4)}
    result = products.compute_skill("temperature", 24, INIT, window_days=4, store=skill_store(missing))
    assert len(result.samples) == 2
    assert len(result.skipped) == 2
    assert result.sources == ["GFS", "ECMWF", "AIFS"]
    products._skill_cache.clear()
    reloaded = products.compute_skill("temperature", 24, INIT, window_days=4, store=products.FieldStore({}))
    assert np.allclose(reloaded.weights["GFS"], result.weights["GFS"])
    assert np.allclose(reloaded.bias["ECMWF"], result.bias["ECMWF"])


def test_skill_refuses_unverifiable_variables_and_off_synoptic_leads() -> None:
    with pytest.raises(SpatialForecastUnavailable, match="observed reference"):
        products.compute_skill("precipitation", 24, INIT, store=skill_store())
    with pytest.raises(SpatialForecastUnavailable, match="00 UTC"):
        products.compute_skill("temperature", 36, INIT, store=skill_store())


def test_adaptive_blend_applies_bias_correction_and_equal_blend_is_mean() -> None:
    store = skill_store()
    equal, provenance = products.blend("temperature", 24, INIT, "equal", store)
    assert equal[0, 0] == pytest.approx((1 + 3 - 2) / 3)
    assert provenance["source_weights"] == pytest.approx({"GFS": 1 / 3, "ECMWF": 1 / 3, "AIFS": 1 / 3})
    adaptive, provenance = products.blend("temperature", 24, INIT, "adaptive", store)
    assert abs(adaptive[0, 0]) < abs(equal[0, 0])
    assert provenance["bias_correction"]["ECMWF"] > 0


def test_layers_spread_and_weights() -> None:
    store = skill_store()
    spread, provenance = products.layer("temperature", 24, INIT, "spread", store=store)
    assert spread[0, 0] == pytest.approx(5.0)
    assert provenance["source_models"] == ["AIFS", "ECMWF", "GFS"]
    weights, provenance = products.layer("temperature", 24, INIT, "weights", source="ECMWF", store=store)
    assert provenance["weight_source"] == "ECMWF"
    assert 0 < weights.mean() < 1 / 3


def test_extremes_levels_agreement_and_hotspots() -> None:
    store = products.FieldStore({
        "GFS": FakeProvider(0, overrides={("precipitation", 48): 200.0, ("precipitation", 24): 50.0,
                                          ("tmax", 36): 30.0, ("wind_speed", 36): 5.0}),
        "ECMWF": FakeProvider(0, overrides={("precipitation", 48): 80.0, ("precipitation", 24): 0.0,
                                            ("tmax", 33): 30.0, ("tmax", 36): 30.0, ("wind_speed", 36): 5.0}),
    })
    guidance = products.extremes(INIT, 1, store)
    rain = next(hazard for hazard in guidance["hazards"] if hazard["hazard"] == "heavy_rain")
    assert rain["status"] == "AVAILABLE"
    assert rain["lead_hours"] == 48
    assert rain["peak"]["value"] == pytest.approx(115.0)  # (150 + 80) / 2
    assert rain["highest_level"] == "Heavy"
    assert rain["agreement"]["all_models_km2"] > 0
    assert rain["agreement"]["by_source_km2"]["GFS"] == rain["agreement"]["by_source_km2"]["ECMWF"] > 0
    assert rain["levels"][1]["area_km2"] == 0
    assert rain["hotspots"]
    heat = next(hazard for hazard in guidance["hazards"] if hazard["hazard"] == "heat")
    assert heat["highest_level"] is None


def test_point_explains_each_source_contribution() -> None:
    explanation = products.point("temperature", 24, INIT, 28.6, 77.2, store=skill_store())
    assert explanation["inside_india"] and explanation["region"] == "North & Himalaya"
    assert {entry["source"] for entry in explanation["sources"]} == {"GFS", "ECMWF", "AIFS"}
    assert sum(entry["weight"] for entry in explanation["sources"]) == pytest.approx(1.0)
    assert explanation["adaptive_blend"] == pytest.approx(sum(entry["contribution"] for entry in explanation["sources"]))
    assert explanation["equal_blend"] == pytest.approx((1 + 3 - 2) / 3)
    assert explanation["spread"] == pytest.approx(5.0)
    with pytest.raises(SpatialForecastUnavailable, match="outside"):
        products.point("temperature", 24, INIT, 50.0, 77.2, store=skill_store())
