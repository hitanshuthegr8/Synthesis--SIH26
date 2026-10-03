"""ECMWF IFS Open Data 0.25 degree temperature provider."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings
from app.spatial.forecast import (
    GRIB_DECODE_LOCK,
    GRID_SPEC,
    decode_variable,
    SpatialForecast,
    SpatialForecastProvider,
    SpatialForecastUnavailable,
    validate_spatial_forecast,
)


ECMWF_PARAMETERS = {
    "temperature": ("2t",),
    "precipitation": ("tp",),
    "wind_speed": ("10u", "10v"),
    "tmax": ("mx2t3",),
}


@dataclass(frozen=True)
class ECMWFProduct:
    initialization: datetime
    lead_hours: int
    variable: str
    file_name: str
    source_url: str
    index_url: str
    model: str = "ifs"


@dataclass(frozen=True)
class ECMWFIndexEntry:
    parameter: str
    level_type: str
    step: int
    message_offset: int
    message_length: int


class ECMWFProductResolver:
    """Resolve current ECMWF IFS 00Z operational forecast products."""

    def __init__(self, base_url: str = settings.ECMWF_BASE_URL, model: str = "ifs") -> None:
        self.base_url = base_url.rstrip("/")
        # "ifs" is the physics-based IFS HRES; "aifs-single" is ECMWF's AI forecast model.
        self.model = model

    def resolve(self, *, initialization: datetime, lead_hours: int, variable: str) -> ECMWFProduct:
        if initialization.tzinfo is None:
            raise ValueError("ECMWF initialization must be timezone-aware")
        if initialization.astimezone(timezone.utc).hour != 0 or initialization.minute or initialization.second:
            raise ValueError("ECMWF MVP supports only 00Z initialization")
        if not 0 <= lead_hours <= 168:
            raise ValueError("ECMWF MVP lead_hours must be between 0 and 168")
        if lead_hours % 3 != 0:
            raise ValueError("ECMWF 0.25 degree products require 3-hour lead increments")
        if variable not in ECMWF_PARAMETERS:
            raise ValueError(f"Unsupported ECMWF variable: {variable}")
        date = initialization.astimezone(timezone.utc).strftime("%Y%m%d")
        cycle = "00"
        file_name = f"{date}{cycle}0000-{lead_hours}h-oper-fc.grib2"
        directory = f"{self.base_url}/{date}/{cycle}z/{self.model}/0p25/oper"
        source_url = f"{directory}/{file_name}"
        return ECMWFProduct(
            initialization=initialization,
            lead_hours=lead_hours,
            variable=variable,
            file_name=file_name,
            source_url=source_url,
            index_url=f"{directory}/{date}{cycle}0000-{lead_hours}h-oper-fc.index",
            model=self.model,
        )


def parse_index(text: str, *, product: ECMWFProduct, parameter: str | None = None) -> ECMWFIndexEntry:
    parameter = parameter or ECMWF_PARAMETERS[product.variable][0]
    for line in text.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if (
            record.get("param") == parameter
            and record.get("levtype") == "sfc"
            and record.get("type") == "fc"
            and record.get("stream") == "oper"
            and int(record.get("step", -1)) == product.lead_hours
        ):
            return ECMWFIndexEntry(
                parameter=parameter,
                level_type="sfc",
                step=product.lead_hours,
                message_offset=int(record["_offset"]),
                message_length=int(record["_length"]),
            )
    raise SpatialForecastUnavailable(f"ECMWF index contains no matching {parameter} surface field")


def parse_index_entries(text: str, *, product: ECMWFProduct) -> list[ECMWFIndexEntry]:
    """All GRIB messages needed for the product's variable (two for wind)."""
    return [parse_index(text, product=product, parameter=parameter) for parameter in ECMWF_PARAMETERS[product.variable]]


class ECMWFReader(Protocol):
    def read(self, path: Path, *, product: ECMWFProduct, index_entries: list[ECMWFIndexEntry]) -> SpatialForecast: ...


class XarrayCfgribECMWFReader:
    def read(self, path: Path, *, product: ECMWFProduct, index_entries: list[ECMWFIndexEntry]) -> SpatialForecast:
        with GRIB_DECODE_LOCK:
            return self._read(path, product=product, index_entries=index_entries)

    def _read(self, path: Path, *, product: ECMWFProduct, index_entries: list[ECMWFIndexEntry]) -> SpatialForecast:
        try:
            import xarray as xr
        except ImportError as error:
            raise SpatialForecastUnavailable("ECMWF decoder unavailable: install xarray, cfgrib, and eccodes") from error
        try:
            dataset = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})
        except Exception as error:
            raise SpatialForecastUnavailable(f"ECMWF GRIB2 decoding failed: {error}") from error
        try:
            latitudes = [float(value) for value in dataset.latitude.values]
            longitudes = [float(value) for value in dataset.longitude.values]
            values, units, source_units = decode_variable(dataset, product.variable, "ECMWF")
            if latitudes and latitudes[0] > latitudes[-1]:
                latitudes.reverse()
                values.reverse()
                latitude_normalization = "reversed descending latitude axis"
            else:
                latitude_normalization = "latitude axis unchanged"
            if longitudes and longitudes[0] < 0:
                longitudes = [value % 360 for value in longitudes]
                order = sorted(range(len(longitudes)), key=longitudes.__getitem__)
                longitudes = [longitudes[index] for index in order]
                values = [[row[index] for index in order] for row in values]
                longitude_normalization = "converted to 0-360 and sorted"
            else:
                longitude_normalization = "longitude axis unchanged"
            latitudes, longitudes, values, subset_note = _subset_target_grid(latitudes, longitudes, values)
            forecast = SpatialForecast(
                source="AIFS" if product.model.startswith("aifs") else "ECMWF",
                variable=product.variable,
                initialization=product.initialization,
                lead_hours=product.lead_hours,
                units=units,
                grid=GRID_SPEC,
                latitudes=latitudes,
                longitudes=longitudes,
                values=values,
                provenance={
                    "model": "AIFS" if product.model.startswith("aifs") else "IFS",
                    "stream": "oper",
                    "type": "fc",
                    "product": product.file_name,
                    "parameter": ",".join(entry.parameter for entry in index_entries),
                    "source_units": source_units,
                    "normalized_units": units,
                    "native_dimensions": {
                        "latitude": len(dataset.latitude),
                        "longitude": len(dataset.longitude),
                    },
                    "native_resolution": 0.25,
                    "target_resolution": GRID_SPEC.resolution,
                    "target_domain": {
                        "south": GRID_SPEC.south,
                        "north": GRID_SPEC.north,
                        "west": GRID_SPEC.west,
                        "east": GRID_SPEC.east,
                    },
                    "latitude_normalization": latitude_normalization,
                    "longitude_normalization": longitude_normalization,
                    "longitude_convention": "0-360 degrees east",
                    "index_url": product.index_url,
                    "selected_byte_ranges": [
                        {"parameter": entry.parameter, "offset": entry.message_offset, "length": entry.message_length}
                        for entry in index_entries
                    ],
                    "source_url": product.source_url,
                    "target_grid_transformation": subset_note,
                    "raw_file": str(path),
                },
            )
            return validate_spatial_forecast(forecast)
        finally:
            dataset.close()


def _subset_target_grid(
    latitudes: list[float], longitudes: list[float], values: list[list[float]]
) -> tuple[list[float], list[float], list[list[float]], str]:
    tolerance = 1e-6
    if not latitudes or not longitudes or not values:
        raise SpatialForecastUnavailable("ECMWF source grid is empty")
    if len(values) != len(latitudes) or any(len(row) != len(longitudes) for row in values):
        raise SpatialForecastUnavailable("ECMWF source dimensions do not match coordinates")
    lat_resolution = abs(latitudes[1] - latitudes[0]) if len(latitudes) > 1 else 0
    lon_resolution = abs(longitudes[1] - longitudes[0]) if len(longitudes) > 1 else 0
    if abs(lat_resolution - GRID_SPEC.resolution) > tolerance or abs(lon_resolution - GRID_SPEC.resolution) > tolerance:
        raise SpatialForecastUnavailable("ECMWF native grid does not match 0.25 degree target; regridding is unavailable")
    lat_indices = [i for i, value in enumerate(latitudes) if GRID_SPEC.south - tolerance <= value <= GRID_SPEC.north + tolerance]
    lon_indices = [i for i, value in enumerate(longitudes) if GRID_SPEC.west - tolerance <= value <= GRID_SPEC.east + tolerance]
    if len(lat_indices) != GRID_SPEC.latitude_count or len(lon_indices) != GRID_SPEC.longitude_count:
        raise SpatialForecastUnavailable("ECMWF native grid does not cover the complete target domain")
    return (
        [latitudes[i] for i in lat_indices],
        [longitudes[i] for i in lon_indices],
        [[values[row][column] for column in lon_indices] for row in lat_indices],
        "direct subset to target domain; no interpolation",
    )


class ECMWFProvider(SpatialForecastProvider):
    def __init__(
        self,
        *,
        resolver: ECMWFProductResolver | None = None,
        reader: ECMWFReader | None = None,
        base_cache_dir: str = settings.ECMWF_CACHE_DIR,
        timeout: float = settings.ECMWF_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.resolver = resolver or ECMWFProductResolver()
        self.reader = reader or XarrayCfgribECMWFReader()
        self.base_cache_dir = Path(base_cache_dir)
        self.timeout = timeout

    def get_forecast(self, *, variable: str, lead_hours: int, initialization: datetime | None = None) -> SpatialForecast:
        init = initialization or datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        product = self.resolver.resolve(initialization=init, lead_hours=lead_hours, variable=variable)
        index_text, index_hit = self._retrieve_index(product)
        entries = parse_index_entries(index_text, product=product)
        path, range_hit = self._retrieve_range(product, *entries)
        forecast = self.reader.read(path, product=product, index_entries=entries)
        return forecast.model_copy(
            update={
                "provenance": {
                    **forecast.provenance,
                    "retrieval_method": "HTTP Range request",
                    "cache": {"path": str(path), "hit": range_hit, "index_hit": index_hit},
                }
            }
        )

    def _retrieve_index(self, product: ECMWFProduct) -> tuple[str, bool]:
        path = self.base_cache_dir / f"{product.file_name}.index"
        if path.exists():
            return path.read_text(encoding="utf-8"), True
        request = Request(product.index_url, headers={"User-Agent": "AIRAVAT/0.1"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return text, False
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise SpatialForecastUnavailable(f"ECMWF index retrieval failed: {error}") from error

    def _retrieve_range(self, product: ECMWFProduct, *entries: ECMWFIndexEntry) -> tuple[Path, bool]:
        parameters = "-".join(entry.parameter for entry in entries)
        path = self.base_cache_dir / f"{product.initialization:%Y%m%d}T00Z_{product.lead_hours:03d}_{parameters}_{product.file_name}.grib2"
        if path.exists():
            return path, True
        try:
            payload = b""
            # GRIB messages are self-delimiting, so separately fetched messages concatenate into one valid file.
            for entry in entries:
                end = entry.message_offset + entry.message_length - 1
                request = Request(
                    product.source_url,
                    headers={
                        "User-Agent": "AIRAVAT/0.1",
                        "Range": f"bytes={entry.message_offset}-{end}",
                    },
                )
                with urlopen(request, timeout=self.timeout) as response:
                    message = response.read()
                if len(message) != entry.message_length:
                    raise SpatialForecastUnavailable("ECMWF byte-range response length does not match index")
                payload += message
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            return path, False
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            path.unlink(missing_ok=True)
            raise SpatialForecastUnavailable(f"ECMWF byte-range retrieval failed: {error}") from error
