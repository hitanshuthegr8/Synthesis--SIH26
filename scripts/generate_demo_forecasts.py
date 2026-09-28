"""Print one named, clearly synthetic AIRAVAT demo forecast scenario."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ingestion.scenarios import SCENARIOS, scenario_forecasts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic demo forecasts.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="normal")
    parser.add_argument("--lead-hours", type=int, default=24)
    args = parser.parse_args()
    print(json.dumps([item.model_dump(mode="json") for item in scenario_forecasts(args.scenario, args.lead_hours)], indent=2))


if __name__ == "__main__":
    main()
