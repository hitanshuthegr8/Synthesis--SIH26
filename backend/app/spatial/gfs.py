"""NOAA GFS 0.25 degree GRIB2 spatial forecast provider."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings
from app.spatial.forecast import GRID_SPEC, SpatialForecast, SpatialForecastProvider, SpatialForecastUnavailable, validate_spatial_forecast


@dataclass(frozen=True)
class GFSVariableSpec:
    name: str
    search: str
    units: str
    accumulation: str | None = None


GFS_VARIABLES = {
    "temperature": GFSVariableSpec("temperature", "var_TMP|lev_2_m_above_ground", "C"),
    "precipitation": GFSVariableSpec("precipitation", "var_APCP", "mm", "source-defined accumulation"),
}


@dataclass(frozen=True)
class GFSProduct:
    initialization: datetime
    lead_hours: int
    variable: str
    file_name: str
    directory: str
    url: str


class GFSProductResolver:
    """Resolve only known GFS 0.25 degree pgrb2 products."""

    def __init__(self, base_url: str = settings.GFS_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def resolve(self, *, initialization: datetime, lead_hours: int, variable: str) -> GFSProduct:
        if initialization.tzinfo is None:
            raise ValueError("GFS initialization must be timezone-aware")
        if initialization.hour != 0 or initialization.minute or initialization.second:
            raise ValueError("GFS MVP supports only 00Z initialization")
        if not 0 <= lead_hours <= 168:
            raise ValueError("GFS MVP lead_hours must be between 0 and 168")
        if lead_hours % 3 != 0:
            raise ValueError("GFS 0.25 degree pgrb2 products require 3-hour lead increments")
        if variable not in GFS_VARIABLES:
            raise ValueError(f"Unsupported GFS variable: {variable}")
        date = initialization.astimezone(timezone.utc).strftime("%Y%m%d")
        cycle = "00"
        file_name = f"gfs.t{cycle}z.pgrb2.0p25.f{lead_hours:03d}"
        directory = f"/gfs.{date}/{cycle}/atmos"
        query = {"file": file_name, "dir": directory}
        if variable == "temperature":
            query.update({"lev_2_m_above_ground": "on", "var_TMP": "on"})
        else:
            query.update({"var_APCP": "on"})
        url = f"{self.base_url}/cgi-bin/filter_gfs_0p25.pl?{urlencode(query)}"
        return GFSProduct(initialization, lead_hours, variable, file_name, directory, url)


class GFSReader(Protocol):
    def read(self, path: Path, *, variable: str, product: GFSProduct) -> SpatialForecast: ...


class XarrayCfgribReader:
    """Decode a local GFS GRIB2 file when optional reader dependencies exist."""

    def read(self, path: Path, *, variable: str, product: GFSProduct) -> SpatialForecast:
        try:
            import xarray as xr
        except ImportError as error:
            raise SpatialForecastUnavailable("GFS decoder unavailable: install xarray, cfgrib, and eccodes") from error
        try:
            dataset = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})
        except Exception as error:
            raise SpatialForecastUnavailable(f"GFS GRIB2 decoding failed: {error}") from error
        try:
            data = next(iter(dataset.data_vars.values()))
            latitudes = [float(value) for value in dataset.latitude.values]
            longitudes = [float(value) for value in dataset.longitude.values]
            values = data.values.tolist()
            source_units = str(data.attrs.get("units", ""))
            units = source_units
            if variable == "temperature":
                if units in {"K", "kelvin"}:
                    values = [[float(value) - 273.15 for value in row] for row in values]
                    units = "C"
                elif units not in {"C", "degC", "°C"}:
                    raise SpatialForecastUnavailable(f"Unsupported GFS temperature units: {units}")
            elif variable == "precipitation":
                step_range = str(data.attrs.get("GRIB_stepRange", ""))
                if not step_range:
                    raise SpatialForecastUnavailable("GFS precipitation accumulation interval is unavailable")
                units = units or "mm"
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
                source="NOAA",
                variable=variable,
                initialization=product.initialization,
                lead_hours=product.lead_hours,
                units=units,
                grid=GRID_SPEC,
                latitudes=latitudes,
                longitudes=longitudes,
                values=values,
                provenance={
                    "model": "GFS",
                    "product": product.file_name,
                    "source_url": product.url,
                    "native_resolution": "0.25 degree product",
                    "target_resolution": GRID_SPEC.resolution,
                    "target_domain": {
                        "south": GRID_SPEC.south,
                        "north": GRID_SPEC.north,
                        "west": GRID_SPEC.west,
                        "east": GRID_SPEC.east,
                    },
                    "source_units": source_units,
                    "normalized_units": units,
                    "latitude_normalization": latitude_normalization,
                    "longitude_normalization": longitude_normalization,
                    "longitude_convention": "0-360 degrees east",
                    "target_grid_transformation": subset_note,
                    "precipitation_step_range": data.attrs.get("GRIB_stepRange") if variable == "precipitation" else None,
                    "raw_file": str(path),
                },
            )
            return validate_spatial_forecast(forecast)
        finally:
            dataset.close()


def _subset_target_grid(
    latitudes: list[float], longitudes: list[float], values: list[list[float]]
) -> tuple[list[float], list[float], list[list[float]], str]:
    """Directly subset a compatible regular source grid; never interpolate."""
    tolerance = 1e-6
    if not latitudes or not longitudes or not values:
        raise SpatialForecastUnavailable("GFS source grid is empty")
    source_resolution = abs(latitudes[1] - latitudes[0]) if len(latitudes) > 1 else 0
    longitude_resolution = abs(longitudes[1] - longitudes[0]) if len(longitudes) > 1 else 0
    if abs(source_resolution - GRID_SPEC.resolution) > tolerance or abs(longitude_resolution - GRID_SPEC.resolution) > tolerance:
        raise SpatialForecastUnavailable("GFS native grid does not match 0.25 degree target; regridding is unavailable")
    lat_indices = [index for index, value in enumerate(latitudes) if GRID_SPEC.south - tolerance <= value <= GRID_SPEC.north + tolerance]
    lon_indices = [index for index, value in enumerate(longitudes) if GRID_SPEC.west - tolerance <= value <= GRID_SPEC.east + tolerance]
    if len(lat_indices) != GRID_SPEC.latitude_count or len(lon_indices) != GRID_SPEC.longitude_count:
        raise SpatialForecastUnavailable("GFS native grid does not cover the complete target domain")
    subset_latitudes = [latitudes[index] for index in lat_indices]
    subset_longitudes = [longitudes[index] for index in lon_indices]
    subset_values = [[values[row][column] for column in lon_indices] for row in lat_indices]
    return subset_latitudes, subset_longitudes, subset_values, "direct subset to target domain; no interpolation"


class GFSProvider(SpatialForecastProvider):
    def __init__(
        self,
        *,
        resolver: GFSProductResolver | None = None,
        reader: GFSReader | None = None,
        cache_dir: str = settings.GFS_CACHE_DIR,
        timeout: float = settings.GFS_REQUEST_TIMEOUT_SECONDS,
        max_download_bytes: int | None = settings.GFS_MAX_DOWNLOAD_BYTES,
    ) -> None:
        self.resolver = resolver or GFSProductResolver()
        self.reader = reader or XarrayCfgribReader()
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self.max_download_bytes = max_download_bytes

    def get_forecast(self, *, variable: str, lead_hours: int, initialization: datetime | None = None) -> SpatialForecast:
        init = initialization or datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        product = self.resolver.resolve(initialization=init, lead_hours=lead_hours, variable=variable)
        path, cache_hit = self._retrieve(product)
        forecast = self.reader.read(path, variable=variable, product=product)
        provenance = {
            **forecast.provenance,
            "cache": {"path": str(path), "hit": cache_hit},
            "retrieval": {"method": "HTTP streaming", "source_url": product.url},
        }
        return forecast.model_copy(update={"provenance": provenance})

    def _retrieve(self, product: GFSProduct) -> tuple[Path, bool]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"gfs_{product.initialization:%Y%m%d}T00Z_{product.lead_hours:03d}_{product.file_name}.grib2"
        if path.exists():
            return path, True
        request = Request(product.url, headers={"User-Agent": "SYNTHESIS/0.1"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                content_length = response.headers.get("Content-Length")
                if self.max_download_bytes and content_length and int(content_length) > self.max_download_bytes:
                    raise SpatialForecastUnavailable("GFS product exceeds configured maximum download size")
                with path.open("wb") as output:
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if self.max_download_bytes and total > self.max_download_bytes:
                            path.unlink(missing_ok=True)
                            raise SpatialForecastUnavailable("GFS product exceeds configured maximum download size")
                        output.write(chunk)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            path.unlink(missing_ok=True)
            raise SpatialForecastUnavailable(f"GFS retrieval failed: {error}") from error
        return path, False
