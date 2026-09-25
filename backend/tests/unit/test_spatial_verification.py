from datetime import datetime, timezone

import pytest

from app.spatial.forecast import GRID_SPEC, SpatialForecast
from app.spatial.verification import (
    SpatialTruth,
    UnavailableTruthProvider,
    compute_error_metrics,
    verify_spatial_forecast,
)


def _forecast(values: list[list[float]], **overrides: object) -> SpatialForecast:
    return SpatialForecast(
        source="NOAA",
        variable=overrides.get("variable", "temperature"),
        initialization=overrides.get("initialization", datetime(2026, 9, 25, tzinfo=timezone.utc)),
        lead_hours=overrides.get("lead_hours", 24),
        units=overrides.get("units", "C"),
        grid=GRID_SPEC,
        latitudes=[5.0 + index * 0.25 for index in range(141)],
        longitudes=[65.0 + index * 0.25 for index in range(141)],
        values=values,
        provenance={"model": "GFS"},
    )


def _truth(values: list[list[float]], **overrides: object) -> SpatialTruth:
    forecast = _forecast(values, **overrides)
    return SpatialTruth(
        source="observation-fixture",
        variable=forecast.variable,
        initialization=forecast.initialization,
        lead_hours=forecast.lead_hours,
        units=forecast.units,
        grid=forecast.grid,
        latitudes=forecast.latitudes,
        longitudes=forecast.longitudes,
        values=forecast.values,
    )


def _full(value: float) -> list[list[float]]:
    return [[value] * 141 for _ in range(141)]


def test_perfect_forecast_metrics_are_zero() -> None:
    result = verify_spatial_forecast(_forecast(_full(10.0)), _truth(_full(10.0)))
    assert result.metrics["mae"] == 0
    assert result.metrics["rmse"] == 0
    assert result.metrics["bias"] == 0
    assert result.metrics["valid_cell_count"] == 19881


def test_known_error_and_positive_negative_bias() -> None:
    positive = verify_spatial_forecast(_forecast(_full(12.0)), _truth(_full(10.0)))
    negative = verify_spatial_forecast(_forecast(_full(8.0)), _truth(_full(10.0)))
    assert positive.metrics["mae"] == 2
    assert positive.metrics["rmse"] == 2
    assert positive.metrics["bias"] == 2
    assert negative.metrics["bias"] == -2


def test_tiny_2x2_metrics_and_absolute_error_field() -> None:
    assert compute_error_metrics([[1.0, 4.0], [7.0, 10.0]], [[2.0, 2.0], [5.0, 14.0]]) == {
        "mae": 2.25,
        "rmse": 2.5,
        "bias": -0.25,
        "valid_cell_count": 4,
        "total_cell_count": 4,
        "invalid_cell_count": 0,
    }


def test_invalid_cells_are_rejected_instead_of_counted_as_zero() -> None:
    with pytest.raises(ValueError, match="finite and non-empty"):
        compute_error_metrics([[1.0, float("nan")]], [[1.0, 1.0]])
    with pytest.raises(ValueError, match="finite and non-empty"):
        compute_error_metrics([[1.0, float("inf")]], [[1.0, 1.0]])


def test_all_invalid_comparison_never_produces_metrics() -> None:
    with pytest.raises(ValueError, match="finite and non-empty"):
        compute_error_metrics([[float("nan")]], [[float("nan")]])


def test_valid_time_is_reported_and_mismatched_truth_claim_is_rejected() -> None:
    forecast = _forecast(_full(10.0))
    truth = _truth(_full(10.0)).model_copy(
        update={"provenance": {"valid_time": "2026-09-26T01:00:00+00:00"}}
    )
    with pytest.raises(ValueError, match="valid UTC times"):
        verify_spatial_forecast(forecast, truth)
    result = verify_spatial_forecast(_forecast(_full(10.0)), _truth(_full(10.0)))
    assert result.provenance["valid_time"].isoformat() == "2026-09-26T00:00:00+00:00"


@pytest.mark.parametrize(
    "override, message",
    [
        ({"variable": "precipitation"}, "variables"),
        ({"units": "K"}, "units"),
        ({"lead_hours": 48}, "lead"),
        ({"initialization": datetime(2026, 9, 25, 3, tzinfo=timezone.utc)}, "initialization"),
    ],
)
def test_metadata_mismatch_is_rejected(override: dict[str, object], message: str) -> None:
    forecast = _forecast(_full(10.0))
    truth = _truth(_full(10.0), **override)
    with pytest.raises(ValueError, match=message):
        verify_spatial_forecast(forecast, truth)


def test_coordinate_and_dimension_mismatch_are_rejected() -> None:
    forecast = _forecast(_full(10.0))
    truth = _truth(_full(10.0)).model_copy(update={"longitudes": [65.1] + forecast.longitudes[1:]})
    with pytest.raises(ValueError, match="coordinates"):
        verify_spatial_forecast(forecast, truth)
    with pytest.raises(ValueError, match="dimensions|shape"):
        compute_error_metrics([[1.0]], [[1.0, 2.0]])


@pytest.mark.parametrize("value", [[float("nan")] * 141, [float("inf")] * 141])
def test_invalid_truth_values_are_rejected(value: list[float]) -> None:
    with pytest.raises(ValueError, match="finite"):
        _truth([value] + _full(1.0)[1:])


def test_provenance_is_verification_metadata() -> None:
    result = verify_spatial_forecast(_forecast(_full(10.0)), _truth(_full(10.0)))
    assert result.provenance["verification_type"] == "deterministic spatial verification"
    assert result.provenance["not_a_confidence_score"] is True
    assert result.provenance["forecast_source"] == "NOAA"


def test_truth_provider_is_explicitly_unavailable() -> None:
    with pytest.raises(Exception, match="truth unavailable"):
        UnavailableTruthProvider().get_truth(
            variable="temperature",
            initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
            lead_hours=24,
        )
