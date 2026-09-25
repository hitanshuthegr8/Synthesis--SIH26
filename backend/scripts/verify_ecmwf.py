"""Manual metadata-only verification for one real ECMWF IFS 2t field."""

from datetime import datetime, timezone

from app.spatial.ecmwf import ECMWFProvider


def main() -> None:
    forecast = ECMWFProvider().get_forecast(
        variable="temperature",
        lead_hours=24,
        initialization=datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
    )
    values = [value for row in forecast.values for value in row]
    print(
        {
            "product": forecast.provenance["product"],
            "initialization": forecast.initialization.isoformat(),
            "lead_hours": forecast.lead_hours,
            "native_dimensions": forecast.provenance["native_dimensions"],
            "target_dimensions": (len(forecast.latitudes), len(forecast.longitudes)),
            "native_resolution": forecast.provenance["native_resolution"],
            "target_extent": {
                "latitude": (min(forecast.latitudes), max(forecast.latitudes)),
                "longitude": (min(forecast.longitudes), max(forecast.longitudes)),
            },
            "source_units": forecast.provenance["source_units"],
            "normalized_units": forecast.units,
            "finite_values": all(value == value and abs(value) != float("inf") for value in values),
            "transformation": forecast.provenance["target_grid_transformation"],
            "provenance": forecast.provenance,
        }
    )


if __name__ == "__main__":
    main()
