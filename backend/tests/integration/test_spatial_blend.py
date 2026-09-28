from datetime import datetime, timezone

from app.spatial.blend import blend_spatial_forecasts
from app.spatial.forecast import GRID_SPEC, SpatialForecast


def _field(source: str, value: float) -> SpatialForecast:
    return SpatialForecast(
        source=source,
        variable="temperature",
        initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        lead_hours=24,
        units="C",
        grid=GRID_SPEC,
        latitudes=[GRID_SPEC.south + i * GRID_SPEC.resolution for i in range(141)],
        longitudes=[GRID_SPEC.west + i * GRID_SPEC.resolution for i in range(141)],
        values=[[value] * 141 for _ in range(141)],
        provenance={"model": source, "fixture": "integration-test"},
    )


def test_gfs_and_ecmwf_produce_valid_synthesis_forecast() -> None:
    result = blend_spatial_forecasts({"GFS": _field("NOAA", 10.0), "ECMWF": _field("ECMWF", 20.0)})
    assert result.source == "AIRAVAT"
    assert result.units == "C"
    assert len(result.values) == 141
    assert len(result.values[0]) == 141
    assert result.values[0][0] == 15.0
