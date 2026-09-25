"""Validated weighted blending for normalized spatial forecasts."""

from math import isfinite
from typing import Mapping

from app.spatial.forecast import SpatialForecast, SpatialForecastUnavailable, validate_spatial_forecast


DEFAULT_WEIGHTS = {"GFS": 0.5, "ECMWF": 0.5}


def blend_spatial_forecasts(
    forecasts: Mapping[str, SpatialForecast],
    weights: Mapping[str, float] | None = None,
) -> SpatialForecast:
    """Return an equal-weight baseline or explicitly weighted spatial blend.

    Weights must name exactly the supplied sources, be finite and non-negative,
    and sum to one within a small floating-point tolerance.
    """
    if not forecasts:
        raise SpatialForecastUnavailable("At least one spatial forecast is required for blending")
    source_names = set(forecasts)
    selected_weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
    if set(selected_weights) != source_names:
        raise ValueError("Blend weights must name exactly the supplied forecast sources")
    if any(not isfinite(value) or value < 0 for value in selected_weights.values()):
        raise ValueError("Blend weights must be finite and non-negative")
    if abs(sum(selected_weights.values()) - 1.0) > 1e-6:
        raise ValueError("Blend weights must sum to 1")

    fields = list(forecasts.values())
    reference = fields[0]
    for forecast in fields:
        _validate_compatible(reference, forecast)

    blended_values = weighted_values(
        {source: forecast.values for source, forecast in forecasts.items()},
        selected_weights,
    )
    provenance = {
        "model": "SYNTHESIS",
        "blend_method": "weighted mean",
        "weight_policy": "equal-weight baseline" if weights is None else "explicit weights",
        "source_models": [
            {"source": forecast.source, "model": forecast.provenance.get("model", source)}
            for source, forecast in forecasts.items()
        ],
        "source_weights": dict(selected_weights),
        "source_provenance": {
            source: forecast.provenance for source, forecast in forecasts.items()
        },
    }
    result = SpatialForecast(
        source="SYNTHESIS",
        variable=reference.variable,
        initialization=reference.initialization,
        lead_hours=reference.lead_hours,
        units=reference.units,
        grid=reference.grid,
        latitudes=list(reference.latitudes),
        longitudes=list(reference.longitudes),
        values=blended_values,
        provenance=provenance,
    )
    return validate_spatial_forecast(result)


def weighted_values(
    values_by_source: Mapping[str, list[list[float]]],
    weights: Mapping[str, float],
) -> list[list[float]]:
    """Blend already validated rectangular numeric fields cell by cell."""
    if not values_by_source:
        raise ValueError("At least one value field is required")
    rows = len(next(iter(values_by_source.values())))
    columns = len(next(iter(values_by_source.values()))[0]) if rows else 0
    if not rows or not columns:
        raise ValueError("Value fields must not be empty")
    for source, values in values_by_source.items():
        if source not in weights or len(values) != rows or any(len(row) != columns for row in values):
            raise ValueError("Value fields must have matching dimensions")
        if any(not isfinite(value) for row in values for value in row):
            raise ValueError("Value fields must contain only finite values")
    return [
        [
            sum(weights[source] * values_by_source[source][row][column] for source in values_by_source)
            for column in range(columns)
        ]
        for row in range(rows)
    ]


def _validate_compatible(reference: SpatialForecast, candidate: SpatialForecast) -> None:
    if candidate.variable != reference.variable:
        raise ValueError("Spatial forecasts must use the same variable")
    if candidate.units != reference.units:
        raise ValueError("Spatial forecasts must use the same units")
    if candidate.initialization != reference.initialization:
        raise ValueError("Spatial forecasts must use the same initialization")
    if candidate.lead_hours != reference.lead_hours:
        raise ValueError("Spatial forecasts must use the same lead")
    if candidate.grid != reference.grid:
        raise ValueError("Spatial forecasts must use the same GridSpec")
    if candidate.latitudes != reference.latitudes or candidate.longitudes != reference.longitudes:
        raise ValueError("Spatial forecasts must use identical latitude and longitude grids")
    if len(candidate.values) != len(reference.values) or any(
        len(candidate_row) != len(reference.longitudes) for candidate_row in candidate.values
    ):
        raise ValueError("Spatial forecasts must use identical dimensions")
    if any(not isfinite(value) for row in candidate.values for value in row):
        raise ValueError("Spatial forecasts must contain only finite values")
