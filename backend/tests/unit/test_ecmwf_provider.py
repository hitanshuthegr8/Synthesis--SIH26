from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.spatial.ecmwf import (
    ECMWFIndexEntry,
    ECMWFProductResolver,
    ECMWFProvider,
    parse_index,
    parse_index_entries,
    _subset_target_grid,
)
from app.spatial.forecast import GRID_SPEC, SpatialForecastUnavailable


def test_ecmwf_resolver_and_index_selection() -> None:
    product = ECMWFProductResolver("https://example.test/forecasts").resolve(
        initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        lead_hours=24,
        variable="temperature",
    )
    assert product.file_name == "20260925000000-24h-oper-fc.grib2"
    assert product.source_url.endswith("/20260925000000-24h-oper-fc.grib2")
    entry = parse_index(
        '{"param":"tp","levtype":"sfc","step":"24","type":"fc","stream":"oper","_offset":0,"_length":2}\n'
        '{"param":"2t","levtype":"sfc","step":"24","type":"fc","stream":"oper","_offset":12,"_length":34}\n',
        product=product,
    )
    assert entry == ECMWFIndexEntry("2t", "sfc", 24, 12, 34)


@pytest.mark.parametrize("lead", [-1, 1, 169])
def test_ecmwf_rejects_unsupported_leads(lead: int) -> None:
    with pytest.raises(ValueError):
        ECMWFProductResolver().resolve(
            initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
            lead_hours=lead,
            variable="temperature",
        )


def test_ecmwf_rejects_non_00z_and_non_temperature() -> None:
    with pytest.raises(ValueError, match="00Z"):
        ECMWFProductResolver().resolve(
            initialization=datetime(2026, 9, 25, 6, tzinfo=timezone.utc),
            lead_hours=24,
            variable="temperature",
        )
    with pytest.raises(ValueError, match="Unsupported ECMWF variable"):
        ECMWFProductResolver().resolve(
            initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
            lead_hours=24,
            variable="humidity",
        )


def test_ecmwf_wind_selects_both_components() -> None:
    product = ECMWFProductResolver("https://example.test/forecasts").resolve(
        initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        lead_hours=24,
        variable="wind_speed",
    )
    entries = parse_index_entries(
        '{"param":"10v","levtype":"sfc","step":"24","type":"fc","stream":"oper","_offset":40,"_length":5}\n'
        '{"param":"10u","levtype":"sfc","step":"24","type":"fc","stream":"oper","_offset":12,"_length":7}\n',
        product=product,
    )
    assert entries == [ECMWFIndexEntry("10u", "sfc", 24, 12, 7), ECMWFIndexEntry("10v", "sfc", 24, 40, 5)]


def test_ecmwf_direct_subset_and_regridding_rejection() -> None:
    latitudes = [GRID_SPEC.south - 1 + index * GRID_SPEC.resolution for index in range(145)]
    longitudes = [GRID_SPEC.west - 1 + index * GRID_SPEC.resolution for index in range(145)]
    values = [[float(row * 1000 + column) for column in range(145)] for row in range(145)]
    subset = _subset_target_grid(latitudes, longitudes, values)
    assert len(subset[0]) == 141
    assert len(subset[1]) == 141
    assert "direct subset" in subset[3]
    with pytest.raises(SpatialForecastUnavailable, match="regridding"):
        _subset_target_grid(
            [GRID_SPEC.south + i * 0.5 for i in range(71)],
            [GRID_SPEC.west + i * 0.5 for i in range(71)],
            [[0.0] * 71 for _ in range(71)],
        )


def test_ecmwf_range_cache_uses_index_byte_length(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Response:
        headers: dict[str, str] = {}

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b"1234"

    seen: list[dict[str, str]] = []

    def fake_urlopen(request: object, **_: object) -> Response:
        seen.append(dict(request.headers))
        return Response()

    monkeypatch.setattr("app.spatial.ecmwf.urlopen", fake_urlopen)
    provider = ECMWFProvider(base_cache_dir=str(tmp_path))
    product = ECMWFProductResolver("https://example.test").resolve(
        initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        lead_hours=24,
        variable="temperature",
    )
    path, hit = provider._retrieve_range(product, ECMWFIndexEntry("2t", "sfc", 24, 10, 4))
    assert path.read_bytes() == b"1234"
    assert hit is False
    assert seen[0]["Range"] == "bytes=10-13"
