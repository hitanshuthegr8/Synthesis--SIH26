"""Minimal ERA5 single-level 2m temperature truth provider."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings
from app.spatial.forecast import GRID_SPEC, SpatialForecastUnavailable
from app.spatial.verification import SpatialTruth, TruthProvider


class ERA5Client(Protocol):
    def retrieve(self, dataset: str, request: dict[str, Any], target: str) -> None: ...


class ERA5Reader(Protocol):
    def read(self, path: Path, *, initialization: datetime, lead_hours: int) -> SpatialTruth: ...


class CdsApiClient:
    def __init__(self) -> None:
        try:
            import cdsapi
        except ImportError as error:
            raise SpatialForecastUnavailable("ERA5 client unavailable: install cdsapi") from error
        if not settings.ERA5_CDS_KEY:
            raise SpatialForecastUnavailable("ERA5 unavailable: ERA5_CDS_KEY is not configured")
        self.client = cdsapi.Client(url=settings.ERA5_CDS_URL, key=settings.ERA5_CDS_KEY)

    def retrieve(self, dataset: str, request: dict[str, Any], target: str) -> None:
        self.client.retrieve(dataset, request, target)


class XarrayERA5Reader:
    def read(self, path: Path, *, initialization: datetime, lead_hours: int) -> SpatialTruth:
        try:
            import xarray as xr
        except ImportError as error:
            raise SpatialForecastUnavailable("ERA5 decoder unavailable: install xarray") from error
        try:
            dataset = xr.open_dataset(path)
        except Exception as error:
            raise SpatialForecastUnavailable(f"ERA5 decoding failed: {error}") from error
        try:
            data = dataset["t2m"] if "t2m" in dataset else next(iter(dataset.data_vars.values()))
            latitudes = [float(value) for value in dataset.latitude.values]
            longitudes = [float(value) for value in dataset.longitude.values]
            values = data.squeeze().values.tolist()
            source_units = str(data.attrs.get("units", ""))
            if source_units not in {"K", "kelvin"}:
                raise SpatialForecastUnavailable(f"Unsupported ERA5 temperature units: {source_units}")
            values = normalize_kelvin_values(values)
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
            if (
                latitudes != [GRID_SPEC.south + i * GRID_SPEC.resolution for i in range(GRID_SPEC.latitude_count)]
                or longitudes != [GRID_SPEC.west + i * GRID_SPEC.resolution for i in range(GRID_SPEC.longitude_count)]
                or len(values) != GRID_SPEC.latitude_count
                or any(len(row) != GRID_SPEC.longitude_count for row in values)
            ):
                raise SpatialForecastUnavailable("ERA5 grid does not exactly match the SYNTHESIS target grid")
            return SpatialTruth(
                source="ERA5",
                variable="temperature",
                initialization=initialization,
                lead_hours=lead_hours,
                units="C",
                grid=GRID_SPEC,
                latitudes=latitudes,
                longitudes=longitudes,
                values=values,
                provenance={
                    "dataset": "reanalysis-era5-single-levels",
                    "variable": "2m_temperature",
                    "valid_time": (
                        initialization.astimezone(timezone.utc)
                        + timedelta(hours=lead_hours)
                    ).isoformat(),
                    "source_units": source_units,
                    "normalized_units": "C",
                    "grid": GRID_SPEC.model_dump(),
                },
            )
        finally:
            dataset.close()


class ERA5Provider(TruthProvider):
    def __init__(
        self,
        *,
        client: ERA5Client | None = None,
        reader: ERA5Reader | None = None,
        cache_dir: str = settings.ERA5_CACHE_DIR,
    ) -> None:
        self.client = client or CdsApiClient()
        self.reader = reader or XarrayERA5Reader()
        self.cache_dir = Path(cache_dir)

    def get_truth(self, *, variable: str, initialization: datetime, lead_hours: int) -> SpatialTruth:
        if variable not in {"temperature", "2m_temperature"}:
            raise ValueError("ERA5 MVP supports only temperature")
        if initialization.tzinfo is None:
            raise ValueError("ERA5 initialization must be timezone-aware")
        valid_time = initialization.astimezone(timezone.utc) + timedelta(hours=lead_hours)
        target = self.cache_dir / f"era5_{valid_time:%Y%m%dT%H00Z}_2t.nc"
        cache_hit = target.exists()
        if not cache_hit:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            try:
                self.client.retrieve(
                    "reanalysis-era5-single-levels",
                    {
                        "product_type": "reanalysis",
                        "variable": "2m_temperature",
                        "year": f"{valid_time.year:04d}",
                        "month": f"{valid_time.month:02d}",
                        "day": f"{valid_time.day:02d}",
                        "time": f"{valid_time.hour:02d}:00",
                        "area": [40, 65, 5, 100],
                        "grid": [0.25, 0.25],
                        "format": "netcdf",
                    },
                    str(target),
                )
            except Exception as error:
                target.unlink(missing_ok=True)
                raise SpatialForecastUnavailable(f"ERA5 retrieval failed: {type(error).__name__}") from error
        truth = self.reader.read(target, initialization=initialization, lead_hours=lead_hours)
        _validate_exact_target_grid(truth)
        return truth.model_copy(
            update={
                "source": "ERA5",
                "provenance": {
                    **truth.provenance,
                    "cache": {"path": str(target), "hit": cache_hit},
                    "retrieval": {"method": "CDS API", "dataset": "reanalysis-era5-single-levels"},
                },
            }
        )


def normalize_kelvin_values(values: list[list[float]]) -> list[list[float]]:
    return [[float(value) - 273.15 for value in row] for row in values]


def _validate_exact_target_grid(truth: SpatialTruth) -> None:
    expected_latitudes = [GRID_SPEC.south + i * GRID_SPEC.resolution for i in range(GRID_SPEC.latitude_count)]
    expected_longitudes = [GRID_SPEC.west + i * GRID_SPEC.resolution for i in range(GRID_SPEC.longitude_count)]
    if (
        truth.grid != GRID_SPEC
        or truth.latitudes != expected_latitudes
        or truth.longitudes != expected_longitudes
        or len(truth.values) != GRID_SPEC.latitude_count
        or any(len(row) != GRID_SPEC.longitude_count for row in truth.values)
    ):
        raise SpatialForecastUnavailable("ERA5 grid does not exactly match the SYNTHESIS target grid")
