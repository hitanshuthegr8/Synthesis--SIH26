"""Seed a SQLite database with clearly synthetic SYNTHESIS demo data."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ingestion.csv_loader import generate_mock_observations
from app.ingestion.mock import MockForecastIngestor
from app.ingestion.scenarios import SCENARIOS, get_scenario, scenario_forecasts, scenario_observation
from app.skill.skill_engine import SimpleSkillEstimator
from app.storage.database import SQLiteDatabase
from app.storage.repositories import SynthesisRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic demo data.")
    parser.add_argument("--database", default="backend/data/synthesis-demo.db")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="normal")
    args = parser.parse_args()

    scenario = get_scenario(args.scenario)
    database_path = Path(args.database)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    repository = SynthesisRepository(SQLiteDatabase(database_path))
    forecasts = scenario_forecasts(args.scenario, lead_hours=24)
    observation = scenario_observation(args.scenario, lead_hours=24)

    history_forecasts = []
    history_observations = []
    for day in range(1, 6):
        initialized = datetime(2025, 12, day, tzinfo=timezone.utc)
        batch = MockForecastIngestor(
            variables=(scenario.variable,), lead_hours=(24,), initialization_time=initialized, seed=day
        ).ingest()
        history_forecasts.extend(batch.valid_forecasts)
        history_observations.extend(generate_mock_observations(
            variables=(scenario.variable,), latitude=19.076, longitude=72.8777,
            initialization_time=initialized, lead_hours=(24,), seed=day,
        ))
    skills = SimpleSkillEstimator().estimate_skills(history_forecasts, history_observations)
    repository.save_forecasts(forecasts)
    repository.save_observations([observation])
    repository.save_model_skills(skills)
    print(json.dumps({"demo_data": True, "scenario": args.scenario, "database": args.database, "forecasts": len(forecasts), "observations": 1, "skill_records": len(skills)}, indent=2))


if __name__ == "__main__":
    main()
