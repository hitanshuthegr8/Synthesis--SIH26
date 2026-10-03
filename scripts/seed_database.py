"""Seed the SQLite database by running the pipeline for all 4 scenarios."""
import sys
from pathlib import Path

# Adds synthesis/backend to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.pipelines.forecast_cycle import run_forecast_cycle

def main():
    scenarios = ["normal", "heavy_rain", "model_conflict", "model_failure"]
    print("Seeding database with all scenarios...")
    for scenario_name in scenarios:
        result = run_forecast_cycle(scenario_name, 24)
        print(f"Scenario: {scenario_name}")
        print(f"  Run ID: {result.run_id}")
        if result.blend:
            print(f"  Blend value: {result.blend.blended_value:.2f}")
            print("  Weights:")
            for model_id, weight in sorted(result.blend.model_weights.items()):
                print(f"    {model_id}: {weight:.3f}")
        else:
            print("  No blend produced.")
        print()

if __name__ == "__main__":
    main()
