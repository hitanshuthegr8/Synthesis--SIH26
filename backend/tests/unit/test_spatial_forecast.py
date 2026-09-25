from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.spatial.forecast import (
    GRID_SPEC,
    GridSpec,
    SpatialForecast,
    SpatialForecastUnavailable,
    UnavailableSpatialForecastProvider,
)


def axes() -> tuple[list[float], list[float]]:
    return (
        [GRID_SPEC.south + index * GRID_SPEC.resolution for index in range(GRID_SPEC.latitude_count)],
        [GRID_SPEC.west + index * GRID_SPEC.resolution for index in range(GRID_SPEC.longitude_count)],
    )


def spatial_values(**overrides: object) -> dict[str, object]:
    latitudes, longitudes = axes()
    payload: dict[str, object] = {
        "source": "fixture-provider",
        "variable": "temperature",
        "initialization": datetime(2026, 9, 25, tzinfo=timezone.utc),
        "lead_hours": 24,
        "units": "C",
        "grid": GRID_SPEC,
        "latitudes": latitudes,
        "longitudes": longitudes,
        "values": [[0.0 for _ in longitudes] for _ in latitudes],
        "provenance": {"fixture": "metadata-only"},
    }
    payload.update(overrides)
    return payload


def test_target_grid_spec_is_explicit() -> None:
    assert GRID_SPEC.model_dump() == {
        "south": 5.0,
        "north": 40.0,
        "west": 65.0,
        "east": 100.0,
        "resolution": 0.25,
        "latitude_count": 141,
        "longitude_count": 141,
    }


def test_grid_spec_rejects_inconsistent_dimensions() -> None:
    with pytest.raises(ValidationError, match="dimensions"):
        GridSpec(latitude_count=140)


def test_spatial_forecast_accepts_valid_coordinate_and_value_shape() -> None:
    forecast = SpatialForecast.model_validate(spatial_values())
    assert len(forecast.latitudes) == 141
    assert len(forecast.values) == 141
    assert len(forecast.values[0]) == 141


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("latitudes", [5.0, 5.5], "Latitude axis length"),
        ("longitudes", [65.0, 65.25], "Longitude axis length"),
        ("values", [[0.0]], "Value array shape"),
    ],
)
def test_spatial_forecast_rejects_malformed_dimensions(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        SpatialForecast.model_validate(spatial_values(**{field: value}))


def test_spatial_forecast_rejects_wrong_resolution() -> None:
    latitudes, longitudes = axes()
    latitudes[1] = 5.3
    with pytest.raises(ValidationError, match="resolution"):
        SpatialForecast.model_validate(spatial_values(latitudes=latitudes, longitudes=longitudes))


def test_spatial_forecast_rejects_missing_values() -> None:
    latitudes, longitudes = axes()
    values = [[0.0 for _ in longitudes] for _ in latitudes]
    values[3][4] = float("nan")
    with pytest.raises(ValidationError, match="missing"):
        SpatialForecast.model_validate(spatial_values(values=values))


def test_unavailable_provider_is_explicit() -> None:
    with pytest.raises(SpatialForecastUnavailable, match="Spatial forecast unavailable"):
        UnavailableSpatialForecastProvider().get_forecast(variable="temperature", lead_hours=24)
