from datetime import datetime, timezone

import pytest

from app.spatial.blend import blend_spatial_forecasts, weighted_values
from app.spatial.forecast import GRID_SPEC, SpatialForecast


def _forecast(source: str, values: list[list[float]], **overrides: object) -> SpatialForecast:
    return SpatialForecast(
        source=source,
        variable=overrides.get("variable", "temperature"),
        initialization=overrides.get("initialization", datetime(2026, 9, 25, tzinfo=timezone.utc)),
        lead_hours=overrides.get("lead_hours", 24),
        units=overrides.get("units", "C"),
        grid=GRID_SPEC,
        latitudes=[5.0, 5.25] if len(values) == 2 else [GRID_SPEC.south + i * GRID_SPEC.resolution for i in range(141)],
        longitudes=[65.0, 65.25] if len(values[0]) == 2 else [GRID_SPEC.west + i * GRID_SPEC.resolution for i in range(141)],
        values=values,
        provenance={"model": source, "fixture": "unit-test"},
    )


def test_equal_weight_blend_is_mathematically_correct() -> None:
    result = blend_spatial_forecasts({"GFS": _forecast("NOAA", [[10.0] * 141] * 141), "ECMWF": _forecast("ECMWF", [[20.0] * 141] * 141)})
    assert result.source == "AIRAVAT"
    assert result.values[0][0] == 15.0
    assert result.provenance["weight_policy"] == "equal-weight baseline"


def test_tiny_2x2_weighted_values_are_mathematically_correct() -> None:
    assert weighted_values(
        {"GFS": [[10.0, 20.0], [30.0, 40.0]], "ECMWF": [[20.0, 30.0], [40.0, 50.0]]},
        {"GFS": 0.5, "ECMWF": 0.5},
    ) == [[15.0, 25.0], [35.0, 45.0]]


def test_explicit_70_30_blend_and_provenance() -> None:
    result = blend_spatial_forecasts(
        {"GFS": _forecast("NOAA", [[10.0] * 141] * 141), "ECMWF": _forecast("ECMWF", [[20.0] * 141] * 141)},
        {"GFS": 0.7, "ECMWF": 0.3},
    )
    assert result.values[0][0] == 13.0
    assert result.provenance["source_weights"] == {"GFS": 0.7, "ECMWF": 0.3}
    assert len(result.provenance["source_provenance"]) == 2


@pytest.mark.parametrize("weights", [{"GFS": 0.4, "ECMWF": 0.4}, {"GFS": -0.1, "ECMWF": 1.1}, {"GFS": float("nan"), "ECMWF": 0.5}])
def test_invalid_weights_are_rejected(weights: dict[str, float]) -> None:
    fields = {"GFS": _forecast("NOAA", [[1.0] * 141] * 141), "ECMWF": _forecast("ECMWF", [[1.0] * 141] * 141)}
    with pytest.raises(ValueError):
        blend_spatial_forecasts(fields, weights)


@pytest.mark.parametrize(
    "override, message",
    [
        ({"lead_hours": 48}, "lead"),
        ({"units": "K"}, "units"),
        ({"variable": "precipitation"}, "variable"),
        ({"initialization": datetime(2026, 9, 25, 3, tzinfo=timezone.utc)}, "initialization"),
    ],
)
def test_mismatched_metadata_is_rejected(override: dict[str, object], message: str) -> None:
    fields = {
        "GFS": _forecast("NOAA", [[1.0] * 141] * 141),
        "ECMWF": _forecast("ECMWF", [[1.0] * 141] * 141, **override),
    }
    with pytest.raises(ValueError, match=message):
        blend_spatial_forecasts(fields)


def test_mismatched_coordinates_and_dimensions_are_rejected() -> None:
    reference = _forecast("NOAA", [[1.0] * 141] * 141)
    candidate = reference.model_copy(update={"source": "ECMWF", "longitudes": [65.1] + reference.longitudes[1:]})
    with pytest.raises(ValueError, match="grids"):
        blend_spatial_forecasts({"GFS": reference, "ECMWF": candidate})

    invalid_shape = reference.model_copy(update={"source": "ECMWF", "values": [[1.0], [1.0]]})
    with pytest.raises(ValueError, match="shape|dimensions"):
        blend_spatial_forecasts({"GFS": reference, "ECMWF": invalid_shape})
