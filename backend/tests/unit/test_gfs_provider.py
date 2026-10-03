from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.spatial.gfs import GFSProductResolver, GFSProvider, _subset_target_grid
from app.spatial.forecast import GRID_SPEC, SpatialForecastUnavailable


def test_gfs_resolver_supports_00z_three_hour_products() -> None:
    product = GFSProductResolver("https://example.test").resolve(
        initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        lead_hours=168,
        variable="temperature",
    )
    assert product.file_name == "gfs.t00z.pgrb2.0p25.f168"
    assert product.directory == "/gfs.20260925/00/atmos"
    assert "filter_gfs_0p25.pl" in product.url
    assert "var_TMP=on" in product.url
    assert "lev_2_m_above_ground=on" in product.url


@pytest.mark.parametrize("lead", [-1, 1, 169])
def test_gfs_resolver_rejects_unsupported_lead(lead: int) -> None:
    with pytest.raises(ValueError):
        GFSProductResolver().resolve(
            initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
            lead_hours=lead,
            variable="temperature",
        )


def test_gfs_resolver_rejects_non_00z_and_unknown_variable() -> None:
    with pytest.raises(ValueError, match="00Z"):
        GFSProductResolver().resolve(
            initialization=datetime(2026, 9, 25, 6, tzinfo=timezone.utc),
            lead_hours=24,
            variable="temperature",
        )
    with pytest.raises(ValueError, match="Unsupported GFS variable"):
        GFSProductResolver().resolve(
            initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
            lead_hours=24,
            variable="humidity",
        )


def test_direct_subsetting_preserves_target_grid_without_interpolation() -> None:
    latitudes = [GRID_SPEC.south - 1 + index * GRID_SPEC.resolution for index in range(145)]
    longitudes = [GRID_SPEC.west - 1 + index * GRID_SPEC.resolution for index in range(145)]
    values = [[float(row * 1000 + column) for column in range(145)] for row in range(145)]
    subset_latitudes, subset_longitudes, subset_values, note = _subset_target_grid(latitudes, longitudes, values)
    assert len(subset_latitudes) == GRID_SPEC.latitude_count
    assert len(subset_longitudes) == GRID_SPEC.longitude_count
    assert len(subset_values) == 141
    assert len(subset_values[0]) == 141
    assert "direct subset" in note


def test_gfs_rejects_source_grid_that_requires_regridding() -> None:
    latitudes = [GRID_SPEC.south + index * 0.5 for index in range(71)]
    longitudes = [GRID_SPEC.west + index * 0.5 for index in range(71)]
    values = [[0.0 for _ in longitudes] for _ in latitudes]
    with pytest.raises(SpatialForecastUnavailable, match="regridding"):
        _subset_target_grid(latitudes, longitudes, values)


def test_gfs_cache_reuses_deterministic_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Response:
        headers: dict[str, str] = {}
        consumed = False

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self, _size: int) -> bytes:
            if self.consumed:
                return b""
            self.consumed = True
            return b"grib-bytes"

    calls = 0

    def fake_urlopen(*_args: object, **_kwargs: object) -> Response:
        nonlocal calls
        calls += 1
        return Response()

    monkeypatch.setattr("app.spatial.gfs.urlopen", fake_urlopen)
    provider = GFSProvider(cache_dir=str(tmp_path))
    product = GFSProductResolver("https://example.test").resolve(
        initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        lead_hours=24,
        variable="temperature",
    )
    first, first_hit = provider._retrieve(product)
    second, second_hit = provider._retrieve(product)
    assert first == second
    assert first.name == "gfs_20260925T00Z_024_temperature_gfs.t00z.pgrb2.0p25.f024.grib2"

    precipitation = GFSProductResolver("https://example.test").resolve(
        initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        lead_hours=24,
        variable="precipitation",
    )
    other, other_hit = provider._retrieve(precipitation)
    assert other != first
    assert other_hit is False
    assert first_hit is False
    assert second_hit is True
    assert calls == 2
