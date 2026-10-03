"""Ingestion module for AIRAVAT."""

from app.ingestion.base import (
    BaseForecastIngestor,
    IngestionBatchResult,
    IngestionErrorRecord,
    PhysicalBounds,
    normalize_and_validate_record,
    normalize_unit_and_value,
    process_forecast_batch,
    validate_physical_plausibility,
)

__all__ = [
    "BaseForecastIngestor",
    "IngestionBatchResult",
    "IngestionErrorRecord",
    "PhysicalBounds",
    "normalize_and_validate_record",
    "normalize_unit_and_value",
    "process_forecast_batch",
    "validate_physical_plausibility",
]
