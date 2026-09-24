"""TASK 004 — Forecast ingestion validation tests."""
from datetime import datetime, timezone

import pytest

from app.ingestion.base import (
    PhysicalBounds,
    normalize_and_validate_record,
    normalize_unit_and_value,
    process_forecast_batch,
    validate_physical_plausibility,
)


def make_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "model_id": "ECMWF",
        "variable": "temperature",
        "latitude": 19.076,
        "longitude": 72.8777,
        "initialization_time": "2026-09-24T00:00:00Z",
        "lead_hours": 48,
        "value": 30.0,
        "unit": "C",
    }
    record.update(overrides)
    return record


@pytest.mark.parametrize(
    ("variable", "value", "unit", "expected_value", "expected_unit"),
    [
        ("temperature", 300.15, "K", 27.0, "C"),
        ("temperature", 86.0, "F", 30.0, "C"),
        ("precipitation", 1.0, "in", 25.4, "mm"),
        ("precipitation", 0.042, "m", 42.0, "mm"),
        ("wind_speed", 36.0, "km/h", 10.0, "m/s"),
        ("wind_speed", 10.0, "knots", 5.1444, "m/s"),
    ],
)
def test_normalize_unit_and_value(
    variable: str,
    value: float,
    unit: str,
    expected_value: float,
    expected_unit: str,
) -> None:
    normalized_value, normalized_unit = normalize_unit_and_value(variable, value, unit)

    assert normalized_value == expected_value
    assert normalized_unit == expected_unit


@pytest.mark.parametrize(
    ("variable", "value", "unit"),
    [
        ("temperature", 30.0, "rankine"),
        ("precipitation", 30.0, "cm"),
        ("wind_speed", 30.0, "mph"),
    ],
)
def test_rejects_unknown_units(variable: str, value: float, unit: str) -> None:
    with pytest.raises(ValueError, match="Unrecognized"):
        normalize_unit_and_value(variable, value, unit)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("temperature", PhysicalBounds.TEMP_MIN_C - 0.1),
        ("temperature", PhysicalBounds.TEMP_MAX_C + 0.1),
        ("precipitation", -0.1),
        ("precipitation", PhysicalBounds.PRECIP_MAX_MM + 0.1),
        ("wind_speed", -0.1),
        ("wind_speed", PhysicalBounds.WIND_MAX_MS + 0.1),
    ],
)
def test_rejects_values_outside_physical_bounds(variable: str, value: float) -> None:
    with pytest.raises(ValueError):
        validate_physical_plausibility(variable, value)


def test_normalization_happens_before_physical_bound_check() -> None:
    with pytest.raises(ValueError, match="outside physical bounds"):
        normalize_and_validate_record(make_record(value=400.0, unit="K"))


def test_normalizes_and_constructs_forecast() -> None:
    forecast = normalize_and_validate_record(
        make_record(value=86.0, unit="degF", initialization_time="2026-09-24T00:00:00Z")
    )

    assert forecast.model_id == "ecmwf"
    assert forecast.value == 30.0
    assert forecast.unit == "C"
    assert forecast.initialization_time == datetime(2026, 9, 24, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "overrides",
    [
        {"model_id": ""},
        {"variable": "humidity"},
        {"latitude": 91.0},
        {"longitude": -181.0},
        {"lead_hours": -1},
        {"value": float("nan")},
    ],
)
def test_rejects_invalid_required_or_domain_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        normalize_and_validate_record(make_record(**overrides))


def test_batch_deduplicates_on_normalized_identity() -> None:
    first = make_record(latitude=19.076041, longitude=72.877741)
    duplicate = make_record(latitude=19.076049, longitude=72.877749, value=31.0)

    result = process_forecast_batch([first, duplicate])

    assert len(result.valid_forecasts) == 1
    assert result.duplicate_count == 1
    assert result.errors == []
    assert result.total_processed == 2


def test_batch_collects_corrupt_records_and_continues() -> None:
    valid = make_record()
    missing_unit = make_record(unit=None)
    invalid_value = make_record(variable="precipitation", value=-1.0, unit="mm")

    result = process_forecast_batch([valid, missing_unit, invalid_value])

    assert len(result.valid_forecasts) == 1
    assert len(result.errors) == 2
    assert result.errors[0].raw_record == missing_unit
    assert "Missing required field" in result.errors[0].reason
    assert result.errors[1].raw_record == invalid_value
    assert "cannot be negative" in result.errors[1].reason
    assert result.is_success is False
