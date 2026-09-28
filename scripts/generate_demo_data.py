"""Generate demo data for all 4 scenarios."""
import json
import sys
from pathlib import Path

# Adds synthesis/backend to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ingestion.scenarios import get_scenario, scenario_forecasts, scenario_observation

def main():
    seed = 42
    scenarios = ["normal", "heavy_rain", "model_conflict", "model_failure"]
    lead_hours = [24, 48, 72, 96, 120, 144, 168]

    try:
        from app.demo.generator import DemoGenerator
        has_generator = True
    except ImportError:
        has_generator = False

    all_forecasts = []
    all_observations = []
    
    for scenario_name in scenarios:
        for lh in lead_hours:
            forecasts = scenario_forecasts(scenario_name, lh)
            for f in forecasts:
                record = {"scenario": scenario_name}
                record.update(f.model_dump(mode="json"))
                all_forecasts.append(record)
                
            obs = scenario_observation(scenario_name, lh)
            record = {"scenario": scenario_name}
            record.update(obs.model_dump(mode="json"))
            all_observations.append(record)
            
    # Writes to data/demo
    output_dir = Path(__file__).resolve().parents[1] / "data" / "demo"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / "scenario_forecasts.jsonl", "w", encoding="utf-8") as f:
        for r in all_forecasts:
            f.write(json.dumps(r) + "\n")
            
    with open(output_dir / "scenario_observations.jsonl", "w", encoding="utf-8") as f:
        for r in all_observations:
            f.write(json.dumps(r) + "\n")
            
    manifest = {
        "dataset_version": "demo-v1",
        "generation_seed": seed,
        "scenarios": scenarios,
        "created_at": "2026-09-24T23:17:58Z",
        "file_count": 2
    }
    with open(output_dir / "MANIFEST.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    print("Generated demo data directly:")
    print(f"Scenarios generated: {scenarios}")
    print(f"Total forecasts: {len(all_forecasts)}")
    print(f"Total observations: {len(all_observations)}")
    print(f"Output directory: {output_dir}")

if __name__ == "__main__":
    main()
