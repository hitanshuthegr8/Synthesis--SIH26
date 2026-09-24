"""Run a small chronological backtest with offline deterministic inputs."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ingestion.csv_loader import generate_mock_observations
from app.ingestion.mock import MockForecastIngestor
from app.verification.backtest import ChronologicalBacktestEngine


def main() -> None:
    forecasts = []
    observations = []
    for day in range(1, 6):
        initialized = datetime(2026, 1, day, tzinfo=timezone.utc)
        ingestor = MockForecastIngestor(variables=("temperature",), lead_hours=(24,), initialization_time=initialized, seed=day)
        forecasts.extend(ingestor.ingest().valid_forecasts)
        observations.extend(generate_mock_observations(variables=("temperature",), latitude=19.076, longitude=72.8777, initialization_time=initialized, lead_hours=(24,), seed=day))
    result = ChronologicalBacktestEngine().run(forecasts, observations)
    print(json.dumps({"blend_count": len(result.blends), "verification_count": len(result.verifications)}, indent=2))


if __name__ == "__main__":
    main()
