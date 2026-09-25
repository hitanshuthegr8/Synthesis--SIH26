from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.spatial.era5 import ERA5Provider
from app.spatial.forecast import SpatialForecastUnavailable


def test_era5_retrieval_failure_is_unavailable_without_error_details(tmp_path: Path) -> None:
    class Client:
        def retrieve(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("credentials should not be exposed")

    with pytest.raises(SpatialForecastUnavailable, match="ERA5 retrieval failed: RuntimeError"):
        ERA5Provider(client=Client(), reader=object(), cache_dir=str(tmp_path)).get_truth(
            variable="temperature",
            initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
            lead_hours=24,
        )
