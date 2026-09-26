"""Generate and verify deterministic, clearly-labelled SYNTHESIS demo data."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.csv_loader import generate_mock_observations
from app.ingestion.mock import MockForecastIngestor
from app.ingestion.scenarios import SCENARIOS, scenario_observation
from app.ingestion.sources import DEMO_SOURCES
from app.skill.skill_engine import SimpleSkillEstimator

DATASET_VERSION = "phase-1.5-demo-v1"
GENERATION_TIME = "2026-01-01T00:00:00Z"
LEAD_HOURS = (24, 48, 72, 96, 120, 144, 168)
PRIMARY_VARIABLES = ("precipitation", "temperature")


class DemoDatasetIntegrityError(ValueError):
    """Raised when generated demo files do not match their manifest."""


def generate_demo_data(output_dir: str | Path, seed: int = 42) -> dict[str, object]:
    """Write stable JSONL benchmark files and a manifest with SHA-256 hashes."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    scenario_records = []
    scenario_observations = []
    for scenario_name in sorted(SCENARIOS):
        for lead_hours in LEAD_HOURS:
            for source in DEMO_SOURCES:
                for record in source.fetch_forecast(scenario_name, lead_hours):
                    scenario_records.append({"scenario": scenario_name, **record.model_dump(mode="json")})
            observation = scenario_observation(scenario_name, lead_hours)
            scenario_observations.append({"scenario": scenario_name, **observation.model_dump(mode="json")})

    historical_forecasts = []
    historical_observations = []
    for day in range(1, 6):
        initialized = datetime(2025, 12, day, tzinfo=timezone.utc)
        forecasts = MockForecastIngestor(
            variables=PRIMARY_VARIABLES, lead_hours=LEAD_HOURS, initialization_time=initialized, seed=seed + day
        ).ingest().valid_forecasts
        observations = generate_mock_observations(
            variables=PRIMARY_VARIABLES,
            latitude=19.076,
            longitude=72.8777,
            initialization_time=initialized,
            lead_hours=LEAD_HOURS,
            seed=seed + day,
        )
        historical_forecasts.extend(item.model_dump(mode="json") for item in forecasts)
        historical_observations.extend(item.model_dump(mode="json") for item in observations)

    skill_records = SimpleSkillEstimator().estimate_skills(
        MockForecastIngestor(
            variables=PRIMARY_VARIABLES,
            lead_hours=LEAD_HOURS,
            initialization_time=datetime(2025, 12, 1, tzinfo=timezone.utc),
            seed=seed,
        ).ingest().valid_forecasts,
        generate_mock_observations(
            variables=PRIMARY_VARIABLES,
            latitude=19.076,
            longitude=72.8777,
            initialization_time=datetime(2025, 12, 1, tzinfo=timezone.utc),
            lead_hours=LEAD_HOURS,
            seed=seed,
        ),
    )

    payloads = {
        "scenario_forecasts.jsonl": scenario_records,
        "scenario_observations.jsonl": scenario_observations,
        "historical_forecasts.jsonl": historical_forecasts,
        "historical_observations.jsonl": historical_observations,
        "historical_skill.jsonl": [item.model_dump(mode="json") for item in skill_records],
    }
    for filename, records in payloads.items():
        _write_jsonl(output / filename, records)

    manifest = {
        "dataset_version": DATASET_VERSION,
        "generation_seed": seed,
        "scenario": "all",
        "created_at": GENERATION_TIME,
        "file_hashes": {filename: _sha256(output / filename) for filename in sorted(payloads)},
    }
    (output / "MANIFEST.json").write_text(_json(manifest) + "\n", encoding="utf-8")
    return manifest


def validate_demo_data(output_dir: str | Path) -> dict[str, object]:
    """Validate every generated data file against its recorded manifest hash."""
    output = Path(output_dir)
    manifest_path = output / "MANIFEST.json"
    if not manifest_path.exists():
        raise DemoDatasetIntegrityError("Demo dataset manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for filename, expected_hash in manifest.get("file_hashes", {}).items():
        candidate = output / filename
        if not candidate.exists() or _sha256(candidate) != expected_hash:
            raise DemoDatasetIntegrityError(f"Demo dataset integrity check failed for {filename}")
    return manifest


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("".join(_json(record) + "\n" for record in records), encoding="utf-8")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
