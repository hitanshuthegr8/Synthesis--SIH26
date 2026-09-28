"""Run the routine AIRAVAT blending workflow for one 00Z cycle (suitable for cron / Task Scheduler)."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.spatial import operations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Blend live GFS and ECMWF IFS forecasts into AIRAVAT products.")
    parser.add_argument("--initialization", help="ISO date of the 00Z cycle, e.g. 2026-09-28 (default: latest complete cycle)")
    parser.add_argument("--variables", nargs="+", default=list(operations.DEFAULT_VARIABLES))
    parser.add_argument("--leads", nargs="+", type=int, default=list(operations.DEFAULT_LEADS))
    parser.add_argument("--days", nargs="+", type=int, default=list(operations.DEFAULT_DAYS))
    args = parser.parse_args()
    initialization = datetime.fromisoformat(args.initialization) if args.initialization else None
    run = operations.execute(operations.create_run(initialization, args.variables, args.leads, args.days))
    for entry in run["log"]:
        print(f"{entry['status']:>11}  {entry['stage']:<24} {entry['message']}")
    print(json.dumps({key: run[key] for key in ("run_id", "initialization", "status", "completed_steps", "total_steps")}, indent=2))
    return 0 if run["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
