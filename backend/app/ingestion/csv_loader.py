"""Offline observation loading and deterministic fixture generation."""
import csv
from datetime import datetime, timedelta
from pathlib import Path
from random import Random
from typing import Iterable

from app.core.constants import VARIABLE_UNITS
from app.domain.forecast import Observation
from app.ingestion.base import normalize_unit_and_value, validate_physical_plausibility
from app.ingestion.mock import _baseline_value


OBSERVATION_COLUMNS = {"variable", "latitude", "longitude", "valid_time", "value", "unit"}


def load_observations_csv(path: str | Path) -> list[Observation]:
    """Load observations from a CSV with explicit headers and normalized units."""
    source = Path(path)
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not OBSERVATION_COLUMNS.issubset(reader.fieldnames):
            raise ValueError(f"Observation CSV must include: {sorted(OBSERVATION_COLUMNS)}")
        observations: list[Observation] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                variable = str(row["variable"]).strip().lower()
                value, unit = normalize_unit_and_value(variable, float(row["value"]), str(row["unit"]))
                validate_physical_plausibility(variable, value)
                observations.append(
                    Observation(
                        variable=variable,
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                        valid_time=datetime.fromisoformat(str(row["valid_time"]).replace("Z", "+00:00")),
                        value=value,
                        unit=unit,
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Invalid observation at CSV line {line_number}: {error}") from error
    return observations


def generate_mock_observations(
    *,
    variables: Iterable[str],
    latitude: float,
    longitude: float,
    initialization_time: datetime,
    lead_hours: Iterable[int],
    seed: int = 42,
) -> list[Observation]:
    """Generate a stable observation set corresponding to the mock forecast grid."""
    rng = Random(seed)
    observations: list[Observation] = []
    for variable in variables:
        if variable not in VARIABLE_UNITS:
            raise ValueError(f"Unsupported mock variable: {variable}")
        for lead in lead_hours:
            value = _baseline_value(variable, lead) + rng.gauss(0.0, 0.25)
            if variable in {"precipitation", "wind_speed"}:
                value = max(0.0, value)
            observations.append(
                Observation(
                    variable=variable,
                    latitude=latitude,
                    longitude=longitude,
                    valid_time=initialization_time + timedelta(hours=lead),
                    value=round(value, 4),
                    unit=VARIABLE_UNITS[variable],
                )
            )
    return observations
