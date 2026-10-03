"""Routine forecast-blending workflow: one run produces every AIRAVAT product for a cycle."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from app.spatial.forecast import SpatialForecastUnavailable
from app.spatial.products import (
    DATA_DIR,
    VARIABLES,
    compute_skill,
    extremes,
    iso,
    latest_cycle,
    layer,
    skill_summary,
    utc_day,
    write_product,
)

DEFAULT_VARIABLES = ("temperature", "precipitation", "wind_speed")
DEFAULT_LEADS = (24, 48, 72)
DEFAULT_DAYS = (0, 1, 2)

_runs: dict[str, dict[str, Any]] = {}
_lock = Lock()
RUNS_DIR = DATA_DIR / "runs"


def _save(run: dict[str, Any]) -> None:
    """Persist the run record so history survives a restart (a run in progress is saved as it was)."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        payload = json.dumps(run, indent=2)
    (RUNS_DIR / f"{run['run_id']}.json").write_text(payload, encoding="utf-8")


def _load(path: Path) -> dict[str, Any] | None:
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if run.get("status") in {"queued", "running"}:
        run["status"] = "interrupted"  # the process that owned it has gone
    return run


def _now() -> str:
    return iso(datetime.now(timezone.utc))


def _log(run: dict[str, Any], stage: str, status: str, message: str) -> None:
    with _lock:
        run["log"].append({"time": _now(), "stage": stage, "status": status, "message": message})
        run["completed_steps"] += 1 if status in {"complete", "unavailable", "failed"} else 0


def execute(run: dict[str, Any]) -> dict[str, Any]:
    """Run every step synchronously; each step records its own outcome and never aborts the others."""
    run["status"] = "running"
    run["started_at"] = _now()
    initialization = datetime.fromisoformat(run["initialization"].replace("Z", "+00:00"))
    for variable in run["variables"]:
        for lead in run["leads"]:
            stage = f"{variable} +{lead}h"
            try:
                values, provenance = layer(variable, lead, initialization, "blend", "equal")
                weighting = "equal"
                skill = None
                if VARIABLES[variable]["verifiable"]:
                    try:
                        skill = skill_summary(compute_skill(variable, lead, initialization))
                        values, provenance = layer(variable, lead, initialization, "blend", "adaptive")
                        weighting = "adaptive"
                    except SpatialForecastUnavailable as error:
                        _log(run, stage, "warning", f"Adaptive weights unavailable, equal weights kept: {error}")
                path = write_product(initialization, f"blend_{variable}_{lead:03d}h", {
                    "provenance": provenance, "weighting": weighting, "skill": skill,
                    "summary": {"min": float(values.min()), "max": float(values.max())},
                })
                run["products"].append({"name": f"{variable} +{lead}h", "weighting": weighting, "path": str(path),
                                        "adaptive_vs_equal_pct": skill["evaluation"]["adaptive_vs_equal_pct"] if skill else None,
                                        "skill_samples": skill["sample_count"] if skill else 0,
                                        "sources": list(provenance.get("source_weights", {}))})
                _log(run, stage, "complete", f"Blended with {weighting} weights")
            except SpatialForecastUnavailable as error:
                _log(run, stage, "unavailable", str(error))
            except Exception as error:  # noqa: BLE001 - one failing product must not stop the run
                _log(run, stage, "failed", f"{type(error).__name__}: {error}")
    for day in run["days"]:
        stage = f"extremes day {day}"
        try:
            guidance = extremes(initialization, day)
            unavailable = [hazard for hazard in guidance["hazards"] if hazard["status"] != "AVAILABLE"]
            if len(unavailable) == len(guidance["hazards"]):
                _log(run, stage, "unavailable", "; ".join(f"{hazard['label']}: {hazard['reason']}" for hazard in unavailable))
                continue
            path = write_product(initialization, f"extremes_day{day}", guidance)
            flagged = [f"{hazard['label']}: {hazard['highest_level']}" for hazard in guidance["hazards"] if hazard.get("highest_level")]
            watch = [
                f"{hazard['label']} ({' + '.join(source for source, km2 in hazard['agreement']['by_source_km2'].items() if km2 > 0)})"
                for hazard in guidance["hazards"]
                if hazard["status"] == "AVAILABLE" and not hazard.get("highest_level") and hazard["agreement"]["some_models_km2"] > 0
            ]
            run["products"].append({"name": f"Extreme guidance day {day}", "path": str(path), "flags": flagged, "watch": watch})
            _log(run, stage, "complete", f"Warnings: {', '.join(flagged) or 'none'}"
                 + (f" · single-model watch: {', '.join(watch)}" if watch else ""))
        except Exception as error:  # noqa: BLE001
            _log(run, stage, "failed", f"{type(error).__name__}: {error}")
    failures = sum(entry["status"] == "failed" for entry in run["log"])
    run["status"] = "failed" if failures and not run["products"] else "complete_with_issues" if failures else "complete"
    run["finished_at"] = _now()
    _save(run)
    return run


def create_run(initialization: datetime | None, variables: list[str] | None, leads: list[int] | None,
               days: list[int] | None) -> dict[str, Any]:
    init = utc_day(initialization) if initialization else latest_cycle()
    selected = list(variables or DEFAULT_VARIABLES)
    unknown = [variable for variable in selected if variable not in VARIABLES]
    if unknown:
        raise ValueError(f"Unsupported variables: {', '.join(unknown)}")
    selected_leads = list(leads or DEFAULT_LEADS)
    selected_days = list(days if days is not None else DEFAULT_DAYS)
    run = {
        "run_id": f"op-{init:%Y%m%d}-{uuid4().hex[:8]}",
        "initialization": iso(init),
        "variables": selected,
        "leads": selected_leads,
        "days": selected_days,
        "status": "queued",
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
        "total_steps": len(selected) * len(selected_leads) + len(selected_days),
        "completed_steps": 0,
        "log": [],
        "products": [],
    }
    with _lock:
        _runs[run["run_id"]] = run
    return run


def start_run(run: dict[str, Any]) -> None:
    Thread(target=execute, args=(run,), daemon=True, name=run["run_id"]).start()


def get_run(run_id: str) -> dict[str, Any] | None:
    if run_id in _runs:
        return _runs[run_id]
    path = RUNS_DIR / f"{run_id}.json"
    return _load(path) if path.exists() else None


def list_runs(limit: int = 30) -> list[dict[str, Any]]:
    runs = {run["run_id"]: run for run in (_load(path) for path in RUNS_DIR.glob("*.json")) if run} if RUNS_DIR.exists() else {}
    runs.update(_runs)
    return sorted(runs.values(), key=lambda run: run["created_at"], reverse=True)[:limit]
