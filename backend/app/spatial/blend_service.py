"""Orchestration for retrieving and blending real spatial forecasts."""

from datetime import datetime

from app.spatial.blend import blend_spatial_forecasts
from app.spatial.ecmwf import ECMWFProvider
from app.spatial.forecast import SpatialForecast, SpatialForecastProvider
from app.spatial.gfs import GFSProvider


class SpatialBlendService:
    """Retrieve both configured deterministic sources for one exact request."""

    def __init__(
        self,
        *,
        gfs_provider: SpatialForecastProvider | None = None,
        ecmwf_provider: SpatialForecastProvider | None = None,
    ) -> None:
        self.gfs_provider = gfs_provider or GFSProvider()
        self.ecmwf_provider = ecmwf_provider or ECMWFProvider()

    def get_blended_forecast(
        self,
        *,
        variable: str,
        lead_hours: int,
        initialization: datetime,
    ) -> SpatialForecast:
        gfs = self.gfs_provider.get_forecast(
            variable=variable,
            lead_hours=lead_hours,
            initialization=initialization,
        )
        ecmwf = self.ecmwf_provider.get_forecast(
            variable=variable,
            lead_hours=lead_hours,
            initialization=initialization,
        )
        return blend_spatial_forecasts({"GFS": gfs, "ECMWF": ecmwf})
