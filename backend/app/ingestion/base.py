"""Base ingestion, validation, and normalization interfaces for SYNTHESIS.

Purpose:
    Enforce Rule 27 data quality pipeline:
    validate -> normalize -> deduplicate -> detect missing values -> detect impossible values.

Guarantees:
    All forecasts entering the system are strictly normalized to standard units:
    - Temperature: Celsius (°C, "C")
    - Precipitation: Millimeters ("mm")
    - Wind Speed: Meters per second ("m/s")
    Physically impossible values (negative rainfall/wind, extreme temperature bounds)
    are rejected with clear diagnostic error records.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Sequence
from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import SUPPORTED_VARIABLES
from app.domain.forecast import Forecast


class PhysicalBounds:
    """Realistic physical boundary thresholds for weather variables."""
    # Celsius
    TEMP_MIN_C: float = -90.0
    TEMP_MAX_C: float = 65.0

    # Precipitation (mm in given time window)
    PRECIP_MIN_MM: float = 0.0
    PRECIP_MAX_MM: float = 2000.0  # World record 24h precipitation is ~1825mm

    # Wind speed (m/s)
    WIND_MIN_MS: float = 0.0
    WIND_MAX_MS: float = 150.0  # Max recorded gust ~113 m/s


class IngestionErrorRecord(BaseModel):
    """Structured record of a rejected forecast record."""
    model_config = ConfigDict(protected_namespaces=())

    raw_record: dict[str, Any]
    reason: str
    field: str | None = None


class IngestionBatchResult(BaseModel):
    """Result of validating and ingesting a batch of forecast records."""
    model_config = ConfigDict(protected_namespaces=())

    valid_forecasts: list[Forecast] = Field(default_factory=list)
    errors: list[IngestionErrorRecord] = Field(default_factory=list)
    duplicate_count: int = 0

    @property
    def total_processed(self) -> int:
        return len(self.valid_forecasts) + len(self.errors) + self.duplicate_count

    @property
    def is_success(self) -> bool:
        return len(self.errors) == 0


def normalize_unit_and_value(variable: str, raw_value: float, raw_unit: str) -> tuple[float, str]:
    """Normalize input unit and value to SYNTHESIS canonical standard units.

    Supported conversions:
    - Temperature:
        - 'C', 'degC', 'celsius' -> 'C' (value unchanged)
        - 'K', 'kelvin' -> 'C' (value - 273.15)
        - 'F', 'degF', 'fahrenheit' -> 'C' ((value - 32) * 5/9)
    - Precipitation:
        - 'mm', 'millimeter', 'millimeters' -> 'mm'
        - 'm', 'meter' -> 'mm' (value * 1000)
        - 'in', 'inch', 'inches' -> 'mm' (value * 25.4)
    - Wind speed:
        - 'm/s', 'mps', 'meter_per_second' -> 'm/s'
        - 'km/h', 'kph', 'kmh' -> 'm/s' (value / 3.6)
        - 'knots', 'kt' -> 'm/s' (value * 0.514444)
    """
    clean_unit = raw_unit.strip().lower()

    if variable == "temperature":
        if clean_unit in {"c", "degc", "celsius", "°c"}:
            return round(raw_value, 4), "C"
        elif clean_unit in {"k", "kelvin"}:
            return round(raw_value - 273.15, 4), "C"
        elif clean_unit in {"f", "degf", "fahrenheit", "°f"}:
            return round((raw_value - 32.0) * 5.0 / 9.0, 4), "C"
        else:
            raise ValueError(f"Unrecognized temperature unit: '{raw_unit}'")

    elif variable == "precipitation":
        if clean_unit in {"mm", "millimeter", "millimeters"}:
            return round(raw_value, 4), "mm"
        elif clean_unit in {"m", "meter", "meters"}:
            return round(raw_value * 1000.0, 4), "mm"
        elif clean_unit in {"in", "inch", "inches"}:
            return round(raw_value * 25.4, 4), "mm"
        else:
            raise ValueError(f"Unrecognized precipitation unit: '{raw_unit}'")

    elif variable == "wind_speed":
        if clean_unit in {"m/s", "mps", "meter_per_second", "meters_per_second"}:
            return round(raw_value, 4), "m/s"
        elif clean_unit in {"km/h", "kph", "kmh"}:
            return round(raw_value / 3.6, 4), "m/s"
        elif clean_unit in {"kt", "knot", "knots"}:
            return round(raw_value * 0.514444, 4), "m/s"
        else:
            raise ValueError(f"Unrecognized wind speed unit: '{raw_unit}'")

    raise ValueError(f"Unsupported variable for unit normalization: '{variable}'")


def validate_physical_plausibility(variable: str, value: float) -> None:
    """Validate that the normalized value satisfies physical boundary rules.

    Raises ValueError if values violate physical laws or historical terrestrial records.
    """
    if variable == "precipitation":
        if value < PhysicalBounds.PRECIP_MIN_MM:
            raise ValueError(f"Precipitation cannot be negative: {value} mm")
        if value > PhysicalBounds.PRECIP_MAX_MM:
            raise ValueError(f"Precipitation exceeds maximum physical threshold: {value} mm")

    elif variable == "wind_speed":
        if value < PhysicalBounds.WIND_MIN_MS:
            raise ValueError(f"Wind speed cannot be negative: {value} m/s")
        if value > PhysicalBounds.WIND_MAX_MS:
            raise ValueError(f"Wind speed exceeds maximum physical threshold: {value} m/s")

    elif variable == "temperature":
        if value < PhysicalBounds.TEMP_MIN_C or value > PhysicalBounds.TEMP_MAX_C:
            raise ValueError(
                f"Temperature {value} °C is outside physical bounds "
                f"[{PhysicalBounds.TEMP_MIN_C}, {PhysicalBounds.TEMP_MAX_C}]"
            )


def normalize_and_validate_record(record: dict[str, Any]) -> Forecast:
    """Process a single raw forecast dictionary through complete validation.

    Performs:
    1. Schema validation (required keys, non-null)
    2. Model ID validation (whitelisted models or non-empty string)
    3. Variable check
    4. Coordinate boundaries check
    5. Unit conversion to canonical standard
    6. Physical plausibility check
    7. Construction of typed Forecast object
    """
    # 1. Check required fields
    required = ["model_id", "variable", "latitude", "longitude", "initialization_time", "lead_hours", "value", "unit"]
    for field in required:
        if field not in record or record[field] is None:
            raise ValueError(f"Missing required field: '{field}'")

    raw_model = str(record["model_id"]).strip().lower()
    if not raw_model:
        raise ValueError("model_id cannot be empty")

    raw_var = str(record["variable"]).strip().lower()
    if raw_var not in SUPPORTED_VARIABLES:
        raise ValueError(f"Variable '{raw_var}' not supported. Allowed: {SUPPORTED_VARIABLES}")

    lat = float(record["latitude"])
    lon = float(record["longitude"])
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitude out of bounds [-90, 90]: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Longitude out of bounds [-180, 180]: {lon}")

    lead_hours = int(record["lead_hours"])
    if lead_hours < 0:
        raise ValueError(f"Lead hours cannot be negative: {lead_hours}")

    raw_val = float(record["value"])
    raw_unit = str(record["unit"])

    # 5. Unit normalization
    norm_val, norm_unit = normalize_unit_and_value(raw_var, raw_val, raw_unit)

    # 6. Physical bounds check
    validate_physical_plausibility(raw_var, norm_val)

    # Parse init time if string
    init_time = record["initialization_time"]
    if isinstance(init_time, str):
        # Support ISO formats with or without Z
        clean_init = init_time.replace("Z", "+00:00")
        init_time = datetime.fromisoformat(clean_init)

    # 7. Construct final typed domain object
    return Forecast(
        model_id=raw_model,
        variable=raw_var,
        latitude=lat,
        longitude=lon,
        initialization_time=init_time,
        lead_hours=lead_hours,
        value=norm_val,
        unit=norm_unit,
    )


def process_forecast_batch(records: Sequence[dict[str, Any]]) -> IngestionBatchResult:
    """Batch ingestion pipeline implementing validation, normalization, and deduplication.

    Deduplication key: (model_id, variable, round(latitude, 4), round(longitude, 4), init_time, lead_hours)
    """
    seen_keys: set[tuple[str, str, float, float, Any, int]] = set()
    result = IngestionBatchResult()

    for item in records:
        try:
            forecast = normalize_and_validate_record(item)
            key = (
                forecast.model_id,
                forecast.variable,
                round(forecast.latitude, 4),
                round(forecast.longitude, 4),
                forecast.initialization_time,
                forecast.lead_hours,
            )
            if key in seen_keys:
                result.duplicate_count += 1
                continue

            seen_keys.add(key)
            result.valid_forecasts.append(forecast)

        except Exception as err:
            result.errors.append(
                IngestionErrorRecord(
                    raw_record=item,
                    reason=str(err),
                )
            )

    return result


class BaseForecastIngestor(ABC):
    """Abstract ingestor interface for pulling and ingesting forecast sources."""

    @abstractmethod
    def ingest(self) -> IngestionBatchResult:
        """Ingest and return a validated batch of forecasts."""
        pass
