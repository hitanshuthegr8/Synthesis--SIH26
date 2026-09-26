from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.demo.generator import DemoDatasetIntegrityError, generate_demo_data, validate_demo_data
from app.ingestion.sources import DEMO_SOURCES, ForecastRecord


def test_demo_sources_return_one_canonical_record_each() -> None:
    records = [source.fetch_forecast("heavy_rain", 24) for source in DEMO_SOURCES]

    assert all(len(batch) == 1 for batch in records)
    assert {batch[0].source_id for batch in records} == {"ecmwf", "gfs", "gefs", "ai"}
    assert all(batch[0].quality_flag == "synthetic_benchmark" for batch in records)
    assert all(batch[0].cell_id == "19.08:72.88" for batch in records)


def test_canonical_record_rejects_inconsistent_valid_time() -> None:
    with pytest.raises(ValidationError, match="valid_time"):
        ForecastRecord(
            source_id="ecmwf", initialization_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            valid_time=datetime(2026, 1, 1, tzinfo=timezone.utc), lead_hours=24,
            variable="temperature", latitude=19.076, longitude=72.8777, cell_id="19.08:72.88", value=30.0, unit="C",
        )


def test_demo_generator_is_deterministic_and_detects_tampering(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = generate_demo_data(first, seed=42)
    second_manifest = generate_demo_data(second, seed=42)

    assert first_manifest == second_manifest
    assert validate_demo_data(first) == first_manifest

    with (first / "scenario_forecasts.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")
    with pytest.raises(DemoDatasetIntegrityError, match="scenario_forecasts"):
        validate_demo_data(first)
