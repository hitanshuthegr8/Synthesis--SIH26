from datetime import datetime, timezone

import pytest

from app.spatial.blend_service import SpatialBlendService
from app.spatial.forecast import GRID_SPEC, SpatialForecast, SpatialForecastUnavailable


def _forecast(source: str, value: float) -> SpatialForecast:
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
        provenance={"model": source, "product": f"{source}-product"},
    )


class RecordingProvider:
    def __init__(self, forecast: SpatialForecast | None = None, error: Exception | None = None) -> None:
        self.forecast = forecast
        self.error = error
        self.calls: list[dict[str, object]] = []

    def get_forecast(self, **kwargs: object) -> SpatialForecast:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        assert self.forecast is not None
        return self.forecast


def test_service_retrieves_both_sources_and_uses_equal_weights() -> None:
    initialization = datetime(2026, 9, 25, tzinfo=timezone.utc)
    gfs = RecordingProvider(_forecast("NOAA", 10.0))
    ecmwf = RecordingProvider(_forecast("ECMWF", 20.0))
    result = SpatialBlendService(gfs_provider=gfs, ecmwf_provider=ecmwf).get_blended_forecast(
        variable="temperature", lead_hours=24, initialization=initialization
    )
    assert result.source == "SYNTHESIS"
    assert result.values[0][0] == 15.0
    assert result.provenance["weight_policy"] == "equal-weight baseline"
    assert result.provenance["source_weights"] == {"GFS": 0.5, "ECMWF": 0.5}
    assert gfs.calls == [{"variable": "temperature", "lead_hours": 24, "initialization": initialization}]
    assert ecmwf.calls == gfs.calls


@pytest.mark.parametrize("missing", ["GFS", "ECMWF"])
def test_service_does_not_fallback_when_either_source_is_unavailable(missing: str) -> None:
    unavailable = SpatialForecastUnavailable(f"{missing} unavailable")
    gfs = RecordingProvider(_forecast("NOAA", 10.0), unavailable if missing == "GFS" else None)
    ecmwf = RecordingProvider(_forecast("ECMWF", 20.0), unavailable if missing == "ECMWF" else None)
    with pytest.raises(SpatialForecastUnavailable, match=missing):
        SpatialBlendService(gfs_provider=gfs, ecmwf_provider=ecmwf).get_blended_forecast(
            variable="temperature",
            lead_hours=168,
            initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        )


def test_service_rejects_provider_metadata_mismatch() -> None:
    gfs = RecordingProvider(_forecast("NOAA", 10.0))
    mismatched = _forecast("ECMWF", 20.0).model_copy(update={"lead_hours": 48})
    ecmwf = RecordingProvider(mismatched)
    with pytest.raises(ValueError, match="lead"):
        SpatialBlendService(gfs_provider=gfs, ecmwf_provider=ecmwf).get_blended_forecast(
            variable="temperature",
            lead_hours=24,
            initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        )
