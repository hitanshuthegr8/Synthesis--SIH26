"""Opt-in live CDS validation; excluded from normal offline pytest runs."""

import os
from datetime import datetime, timezone

import pytest

from app.spatial.era5 import ERA5Provider


@pytest.mark.skipif(
    os.getenv("RUN_ERA5_LIVE") != "1" or not os.getenv("ERA5_CDS_KEY"),
    reason="Set RUN_ERA5_LIVE=1 and ERA5_CDS_KEY to run the live CDS check",
)
def test_live_era5_target_grid() -> None:
    truth = ERA5Provider().get_truth(
        variable="temperature",
        initialization=datetime(2026, 9, 25, tzinfo=timezone.utc),
        lead_hours=24,
    )
    values = [value for row in truth.values for value in row]
    assert (len(truth.latitudes), len(truth.longitudes)) == (141, 141)
    assert truth.latitudes[0] == 5.0
    assert truth.latitudes[-1] == 40.0
    assert truth.longitudes[0] == 65.0
    assert truth.longitudes[-1] == 100.0
    assert truth.units == "C"
    assert all(value == value and abs(value) != float("inf") for value in values)
    assert truth.provenance["dataset"] == "reanalysis-era5-single-levels"
    assert truth.provenance["cache"]["hit"] in {True, False}
