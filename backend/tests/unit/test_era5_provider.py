from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.spatial.era5 import ERA5Provider, normalize_kelvin_values
from app.spatial.forecast import GRID_SPEC, SpatialForecastUnavailable
from app.spatial.verification import SpatialTruth


def test_era5_request_uses_valid_time_and_caches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    requests: list[dict] = []

    class Client:
        def retrieve(self, _dataset: str, request: dict, target: str) -> None:
            requests.append(request)
            Path(target).write_bytes(b"fixture")

    class Reader:
        def read(self, _path: Path, *, initialization: datetime, lead_hours: int) -> SpatialTruth:
            axes = [5.0 + i * 0.25 for i in range(141)]
            return SpatialTruth(
                source="ERA5", variable="temperature", initialization=initialization,
                lead_hours=lead_hours, units="C", grid=GRID_SPEC,
                latitudes=axes, longitudes=[65.0 + i * 0.25 for i in range(141)],
                values=[[1.0] * 141 for _ in range(141)],
            )

    provider = ERA5Provider(client=Client(), reader=Reader(), cache_dir=str(tmp_path))
    init = datetime(2026, 9, 25, tzinfo=timezone.utc)
    first = provider.get_truth(variable="temperature", initialization=init, lead_hours=24)
    second = provider.get_truth(variable="temperature", initialization=init, lead_hours=24)
    assert requests[0]["day"] == "26"
    assert requests[0]["time"] == "00:00"
    assert requests[0]["grid"] == [0.25, 0.25]
    assert len(requests) == 1
    assert first.provenance["cache"]["hit"] is False
    assert second.provenance["cache"]["hit"] is True
    assert first.values == second.values


def test_era5_rejects_unsupported_variable() -> None:
    with pytest.raises(ValueError, match="only temperature"):
        ERA5Provider(client=object(), reader=object()).get_truth(
            variable="precipitation",
            initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
            lead_hours=24,
        )


def test_era5_normalizes_kelvin_to_celsius() -> None:
    assert normalize_kelvin_values([[273.15, 274.15]]) == [[0.0, 1.0]]


def test_era5_grid_mismatch_is_unavailable() -> None:
    class Reader:
        def read(self, _path: Path, *, initialization: datetime, lead_hours: int) -> SpatialTruth:
            axes = [5.0 + i * 0.5 for i in range(71)]
            return SpatialTruth.model_construct(
                source="ERA5", variable="temperature", initialization=initialization,
                lead_hours=lead_hours, units="C", grid=GRID_SPEC,
                latitudes=axes, longitudes=axes, values=[[1.0] * 71 for _ in range(71)],
            )

    class Client:
        def retrieve(self, _dataset: str, _request: dict, target: str) -> None:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            Path(target).write_bytes(b"fixture")

    with pytest.raises(SpatialForecastUnavailable, match="does not exactly match"):
        ERA5Provider(client=Client(), reader=Reader(), cache_dir="").get_truth(
            variable="temperature",
            initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
            lead_hours=24,
        )
