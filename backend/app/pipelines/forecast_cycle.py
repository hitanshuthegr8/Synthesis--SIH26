"""Deterministic Phase 1.5 forecast-cycle orchestration and trace registry."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel, Field

from app.api.dependencies import demo_skills
from app.blending.engine import BlendEngine
from app.blending.explanation import ExplanationEngine
from app.blending.weights import calculate_base_weights, normalize_trust_scores
from app.domain.forecast import Forecast
from app.domain.model import ModelSkill
from app.domain.uncertainty import BlendResult
from app.domain.verification import ForecastAutopsy, VerificationResult
from app.ingestion.base import process_forecast_batch
from app.ingestion.scenarios import get_scenario, scenario_forecasts, scenario_observation
from app.regime.classifier import RuleBasedRegimeClassifier
from app.uncertainty.disagreement import DisagreementEngine
from app.uncertainty.engine import UncertaintyEngine
from app.verification.autopsy import ForecastAutopsyEngine
from app.core.config import settings
from app.core.constants import SUPPORTED_MODELS
from app.storage.database import SQLiteDatabase
from app.storage.repositories import SynthesisRepository


class ComputationStep(BaseModel):
    name: str
    status: str = "complete"
    duration_ms: int = Field(ge=0)
    details: list[str] = Field(default_factory=list)


class ComputationTrace(BaseModel):
    run_id: str
    status: str
    duration_ms: int = Field(ge=0)
    created_at: datetime
    cycle_time: datetime
    scenario: str
    variable: str
    lead_hours: int
    region: str = "Maharashtra"
    dataset_version: str = "demo-v1"
    algorithm_version: str = "phase-1.5"
    configuration_hash: str
    stale_from_run_id: str | None = None
    source_availability: dict[str, bool]
    steps: list[ComputationStep]
    inputs: list[Forecast]
    skill_records: list[ModelSkill]
    output: BlendResult


class ForecastCycleResult(BaseModel):
    run_id: str
    status: str
    forecasts: list[Forecast]
    reliability: list[ModelSkill]
    blend: BlendResult
    verification: VerificationResult
    autopsy: ForecastAutopsy
    trace: ComputationTrace


class NoUsableSourcesError(RuntimeError):
    """Raised when validation leaves a cycle without a forecast to blend."""


def _database_path() -> Path:
    database_url = settings.DATABASE_URL
    prefix = "sqlite:///"
    path = Path(database_url.removeprefix(prefix) if database_url.startswith(prefix) else database_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class ForecastCycleRegistry:
    """Fast cache backed by SQLite for replay and trace retrieval after restart."""

    def __init__(self, repository: SynthesisRepository | None = None) -> None:
        self._runs: dict[str, ForecastCycleResult] = {}
        self._lock = Lock()
        self._repository = repository or SynthesisRepository(SQLiteDatabase(_database_path()))

    def save(self, result: ForecastCycleResult) -> None:
        with self._lock:
            self._runs[result.run_id] = result
        self._repository.save_forecast_cycle(result.run_id, result.model_dump_json())

    def get(self, run_id: str) -> ForecastCycleResult | None:
        with self._lock:
            cached = self._runs.get(run_id)
        if cached is not None:
            return cached
        payload = self._repository.get_forecast_cycle(run_id)
        if payload is None:
            return None
        restored = ForecastCycleResult.model_validate_json(payload)
        with self._lock:
            self._runs[run_id] = restored
        return restored

    def latest(self) -> ForecastCycleResult | None:
        with self._lock:
            if self._runs:
                return max(self._runs.values(), key=lambda result: result.trace.created_at)
        payload = self._repository.get_latest_forecast_cycle()
        if payload is None:
            return None
        restored = ForecastCycleResult.model_validate_json(payload)
        with self._lock:
            self._runs[restored.run_id] = restored
        return restored


cycle_registry = ForecastCycleRegistry()


def run_forecast_cycle(
    scenario_name: str,
    lead_hours: int = 24,
    registry: ForecastCycleRegistry | None = None,
    unavailable_sources: tuple[str, ...] = (),
    corrupt_sources: tuple[str, ...] = (),
) -> ForecastCycleResult:
    """Run the complete offline cycle and preserve each computational step."""
    started_at = perf_counter()
    scenario = get_scenario(scenario_name)
    run_id = f"SYN-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}"
    steps: list[ComputationStep] = []

    step_started = perf_counter()
    unavailable = set(unavailable_sources)
    corrupt = set(corrupt_sources)
    active_registry = registry or cycle_registry
    raw_forecasts = [
        forecast for forecast in scenario_forecasts(scenario_name, lead_hours)
        if forecast.model_id not in unavailable
    ]
    steps.append(_step("source_ingestion", step_started, [f"{len(raw_forecasts)}/4 synthetic benchmark sources received"]))

    if not raw_forecasts:
        return _stale_or_unavailable(active_registry, scenario.variable, unavailable, corrupt)

    step_started = perf_counter()
    raw_records = [item.model_dump() for item in raw_forecasts]
    for record in raw_records:
        if record["model_id"] in corrupt:
            record["value"] = float("nan")
    ingestion = process_forecast_batch(raw_records)
    if not ingestion.valid_forecasts:
        return _stale_or_unavailable(active_registry, scenario.variable, unavailable, corrupt)
    forecasts = ingestion.valid_forecasts
    cycle_time = forecasts[0].initialization_time
    configuration_hash = _configuration_hash(scenario_name, scenario.variable, lead_hours)
    steps.append(_step("validation_normalization", step_started, [
        f"{len(forecasts)} valid records",
        f"{len(ingestion.errors)} corrupt records quarantined",
        f"{ingestion.duplicate_count} duplicate records removed",
    ]))

    step_started = perf_counter()
    skill_records = [item for item in demo_skills(scenario.variable, lead_hours) if item.metric == "mae"]
    base_weights = calculate_base_weights(skill_records)
    steps.append(_step("historical_skill", step_started, [f"{len(skill_records)} source MAE records", "DEMO DATASET: 5 verification cases per source"]))

    step_started = perf_counter()
    regime = RuleBasedRegimeClassifier().classify(forecasts)
    disagreement = DisagreementEngine().calculate(forecasts)
    steps.append(_step("context", step_started, [f"Regime: {regime.name.value}", f"Disagreement: {disagreement.level.value}"]))

    step_started = perf_counter()
    weights = normalize_trust_scores({forecast.model_id: base_weights[forecast.model_id] for forecast in forecasts})
    weights = _apply_failure_penalty(weights, scenario_name)
    weight_details = [f"{model_id.upper()}: {weight:.1%}" for model_id, weight in sorted(weights.items())]
    if scenario_name == "model_failure":
        weight_details.append("GFS source flagged anomalous; availability penalty applied")
    steps.append(_step("adaptive_weighting", step_started, weight_details))

    step_started = perf_counter()
    core_blend = BlendEngine().blend(forecasts, weights)
    historical_mae = sum(item.score for item in skill_records) / len(skill_records)
    degraded = len(forecasts) < len(SUPPORTED_MODELS)
    uncertainty = UncertaintyEngine().estimate(
        core_blend.value,
        disagreement,
        historical_mae=historical_mae,
        recent_mae=historical_mae if degraded else None,
    )
    explanation = ExplanationEngine().generate(core_blend.weights, regime, disagreement, uncertainty)
    if len(forecasts) == 1:
        explanation.append("SINGLE SOURCE FALLBACK: uncertainty is widened because only one validated source is available.")
    elif degraded:
        explanation.append("DEGRADED SOURCE SET: unavailable or corrupt sources were excluded and uncertainty was widened.")
    blend = BlendResult(
        variable=scenario.variable,
        latitude=forecasts[0].latitude,
        longitude=forecasts[0].longitude,
        valid_time=(forecasts[0].initialization_time + timedelta(hours=lead_hours)).isoformat().replace("+00:00", "Z"),
        blended_value=core_blend.value,
        lower_bound=uncertainty.lower_bound,
        upper_bound=uncertainty.upper_bound,
        model_weights=core_blend.weights,
        disagreement=disagreement,
        regime=regime.name.value,
        regime_confidence=regime.confidence,
        explanation=explanation,
        fallback_mode=core_blend.fallback_mode,
        run_id=run_id,
        processing_time_ms=0,
        algorithm="Adaptive Skill-Context Blender",
        verification_dataset="DEMO DATASET",
        cycle_time=cycle_time,
        region="Maharashtra",
        dataset_version="demo-v1",
        configuration_hash=configuration_hash,
    )
    steps.append(_step("blend_uncertainty", step_started, [f"Blend: {blend.blended_value:.2f} {forecasts[0].unit}", f"Range: {uncertainty.lower_bound:.2f} to {uncertainty.upper_bound:.2f}"]))

    step_started = perf_counter()
    verification, autopsy = ForecastAutopsyEngine().analyze(blend, forecasts, scenario_observation(scenario_name, lead_hours))
    steps.append(_step("verification_autopsy", step_started, [f"Absolute error: {verification.absolute_error:.2f} {forecasts[0].unit}"]))

    duration_ms = round((perf_counter() - started_at) * 1000)
    blend.processing_time_ms = duration_ms
    trace = ComputationTrace(
        run_id=run_id,
        status="degraded" if degraded else "complete",
        duration_ms=duration_ms,
        created_at=datetime.now(timezone.utc),
        cycle_time=cycle_time,
        scenario=scenario_name,
        variable=scenario.variable,
        lead_hours=lead_hours,
        configuration_hash=configuration_hash,
        source_availability={model_id: model_id in {item.model_id for item in forecasts} for model_id in SUPPORTED_MODELS},
        steps=steps,
        inputs=forecasts,
        skill_records=skill_records,
        output=blend,
    )
    result = ForecastCycleResult(run_id=run_id, status=trace.status, forecasts=forecasts, reliability=skill_records, blend=blend, verification=verification, autopsy=autopsy, trace=trace)
    active_registry.save(result)
    return result


def replay_forecast_cycle(run_id: str) -> ForecastCycleResult:
    frozen = cycle_registry.get(run_id)
    if frozen is None:
        raise KeyError(run_id)
    return run_forecast_cycle(frozen.trace.scenario, frozen.trace.lead_hours)


def _apply_failure_penalty(weights: dict[str, float], scenario_name: str) -> dict[str, float]:
    if scenario_name != "model_failure":
        return weights
    adjusted = dict(weights)
    adjusted["gfs"] *= 0.1
    return normalize_trust_scores(adjusted)


def _step(name: str, started_at: float, details: list[str]) -> ComputationStep:
    return ComputationStep(name=name, duration_ms=round((perf_counter() - started_at) * 1000), details=details)


def _configuration_hash(scenario: str, variable: str, lead_hours: int) -> str:
    """Fingerprint the effective configuration used by this cycle."""
    configuration = {
        "algorithm_version": "phase-1.5",
        "dataset_version": "demo-v1",
        "scenario": scenario,
        "variable": variable,
        "lead_hours": lead_hours,
        "disagreement_thresholds": [
            settings.DISAGREEMENT_LOW,
            settings.DISAGREEMENT_MEDIUM,
            settings.DISAGREEMENT_HIGH,
        ],
        "regime_heavy_rain_mm": settings.REGIME_HEAVY_RAIN_MM,
    }
    encoded = json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stale_or_unavailable(
    registry: ForecastCycleRegistry,
    variable: str,
    unavailable: set[str],
    corrupt: set[str],
) -> ForecastCycleResult:
    previous = registry.latest()
    if previous is None or previous.blend.variable != variable:
        raise NoUsableSourcesError("No usable source forecasts remain after source validation")

    run_id = f"SYN-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}"
    explanation = list(previous.blend.explanation)
    explanation.append("STALE: all current sources failed; this is the last successful forecast for the requested variable.")
    blend = previous.blend.model_copy(update={
        "run_id": run_id,
        "explanation": explanation,
        "processing_time_ms": 0,
    })
    stale_step = ComputationStep(
        name="source_ingestion",
        status="failed",
        duration_ms=0,
        details=[
            "0/4 synthetic benchmark sources received",
            f"Unavailable sources: {', '.join(sorted(unavailable)) or 'none'}",
            f"Corrupt sources: {', '.join(sorted(corrupt)) or 'none'}",
            f"Serving last good forecast from {previous.run_id}",
        ],
    )
    trace = previous.trace.model_copy(update={
        "run_id": run_id,
        "status": "stale",
        "created_at": datetime.now(timezone.utc),
        "duration_ms": 0,
        "source_availability": {model_id: False for model_id in SUPPORTED_MODELS},
        "steps": [*previous.trace.steps, stale_step],
        "output": blend,
        "stale_from_run_id": previous.run_id,
    })
    result = previous.model_copy(update={
        "run_id": run_id,
        "status": "stale",
        "blend": blend,
        "verification": previous.verification.model_copy(update={"run_id": run_id}),
        "autopsy": previous.autopsy.model_copy(update={"run_id": run_id}),
        "trace": trace,
    })
    registry.save(result)
    return result
