"""Real-data AIRAVAT products built from live NWP and AI forecast fields.

Sources: NOAA GFS and ECMWF IFS (physics-based NWP) and ECMWF AIFS (machine
learning). Everything here is derived from retrieved model output; nothing is
synthesised. Where a product cannot be supported honestly (for example rainfall
skill, which needs an observed rainfall reference), it raises
``SpatialForecastUnavailable`` with the reason instead of inventing numbers.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from scipy.ndimage import uniform_filter

from app.core.config import settings
from app.spatial.ecmwf import ECMWFProductResolver, ECMWFProvider
from app.spatial.forecast import GRID_SPEC, SpatialForecastProvider, SpatialForecastUnavailable
from app.spatial.gfs import GFSProvider

SOURCES: dict[str, dict[str, str]] = {
    "GFS": {"label": "NOAA GFS", "model": "GFS", "kind": "Physics NWP", "centre": "NOAA/NCEP"},
    "ECMWF": {"label": "ECMWF IFS", "model": "IFS", "kind": "Physics NWP", "centre": "ECMWF"},
    "AIFS": {"label": "ECMWF AIFS", "model": "AIFS", "kind": "AI / ML model", "centre": "ECMWF"},
}
ANALYSIS_SOURCES = ("GFS", "ECMWF")  # AIFS starts from the IFS analysis, so it has no analysis of its own

VARIABLES: dict[str, dict[str, Any]] = {
    "temperature": {"label": "2 m temperature", "units": "C", "verifiable": True,
                    "note": "Instantaneous 2 m air temperature at the valid time."},
    "tmax": {"label": "Afternoon max temperature", "units": "C", "verifiable": False,
             "note": "Maximum 2 m temperature over the 6 h ending at the valid time (12 UTC ≈ 17:30 IST catches the afternoon peak). AIFS does not publish it."},
    "precipitation": {"label": "24 h rainfall", "units": "mm", "verifiable": False,
                      "note": "Accumulation over the 24 h ending at the valid time (0 to lead when lead < 24 h)."},
    "wind_speed": {"label": "10 m wind speed", "units": "m/s", "verifiable": True,
                   "note": "Magnitude of the 10 m u/v wind at the valid time."},
}

# IMD 24 h rainfall categories; heat uses absolute afternoon-maximum thresholds (no climatological departure);
# wind uses Beaufort 6/7/8 lower bounds.
HAZARDS: dict[str, dict[str, Any]] = {
    "heavy_rain": {"label": "Heavy rainfall", "variable": "precipitation", "units": "mm/24 h",
                   "levels": [(64.5, "Heavy"), (115.6, "Very heavy"), (204.5, "Extremely heavy")]},
    "heat": {"label": "Heat", "variable": "tmax", "units": "°C",
             "levels": [(40.0, "Heat stress"), (45.0, "Heat wave"), (47.0, "Severe heat wave")]},
    "high_wind": {"label": "High wind", "variable": "wind_speed", "units": "m/s",
                  "levels": [(10.8, "Strong wind"), (13.9, "Near gale"), (17.2, "Gale")]},
}

REGIONS = (
    ("northeast", "Northeast"),
    ("north", "North & Himalaya"),
    ("central", "Northwest & Central"),
    ("east", "East"),
    ("south", "Peninsular South"),
)

SHRINKAGE_SAMPLES = 2.0
SMOOTHING_CELLS = 9  # ±1° box: regional rather than single-cell skill
DATA_DIR = Path(settings.GFS_CACHE_DIR).parent
PRODUCTS_DIR = DATA_DIR / "products"
SKILL_DIR = DATA_DIR / "skill"

LATITUDES = np.array([GRID_SPEC.south + index * GRID_SPEC.resolution for index in range(GRID_SPEC.latitude_count)])
LONGITUDES = np.array([GRID_SPEC.west + index * GRID_SPEC.resolution for index in range(GRID_SPEC.longitude_count)])


def utc_day(value: datetime) -> datetime:
    value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# --------------------------------------------------------------------------- geography

@lru_cache(maxsize=1)
def india_mask() -> np.ndarray:
    """Boolean (lat, lon) mask of grid cells inside India, by even-odd ray casting."""
    geojson = json.loads((Path(__file__).parent / "assets" / "india.json").read_text(encoding="utf-8"))
    rings: list[np.ndarray] = []
    for feature in geojson["features"]:
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        rings.extend(np.asarray(ring, dtype=float) for polygon in polygons for ring in polygon)
    lon, lat = np.meshgrid(LONGITUDES, LATITUDES)
    inside = np.zeros(lon.shape, dtype=bool)
    for ring in rings:
        for (ax, ay), (bx, by) in zip(ring[:-1], ring[1:]):
            if ay == by:
                continue
            crosses = (ay > lat) != (by > lat)
            x_at = ax + (lat - ay) * (bx - ax) / (by - ay)
            inside ^= crosses & (lon < x_at)
    return inside


@lru_cache(maxsize=1)
def region_masks() -> dict[str, np.ndarray]:
    lon, lat = np.meshgrid(LONGITUDES, LATITUDES)
    india = india_mask()
    northeast = lon >= 88.5
    regions = {
        "northeast": northeast,
        "north": ~northeast & (lat >= 28),
        "central": ~northeast & (lat >= 21) & (lat < 28) & (lon < 83),
        "east": ~northeast & (lat >= 21) & (lat < 28) & (lon >= 83),
        "south": ~northeast & (lat < 21),
    }
    return {key: india & mask for key, mask in regions.items()}


@lru_cache(maxsize=1)
def cell_area_km2() -> np.ndarray:
    side = GRID_SPEC.resolution * 111.32
    return np.repeat((side * side * np.cos(np.radians(LATITUDES)))[:, None], GRID_SPEC.longitude_count, axis=1)


# --------------------------------------------------------------------------- field retrieval

class FieldStore:
    """Cached access to normalised model fields plus the derived variables AIRAVAT uses."""

    def __init__(self, providers: dict[str, SpatialForecastProvider] | None = None, capacity: int = 768) -> None:
        self._providers = providers
        self._cache: OrderedDict[tuple, np.ndarray] = OrderedDict()
        self._capacity = capacity
        self._lock = Lock()

    def enabled(self, source: str) -> bool:
        if self._providers is not None:
            return source in self._providers
        return bool(getattr(settings, f"{'AIFS' if source == 'AIFS' else source}_ENABLED", False))

    def _provider(self, source: str) -> SpatialForecastProvider:
        if self._providers is not None:
            if source not in self._providers:
                raise SpatialForecastUnavailable(f"{source} provider is not configured")
            return self._providers[source]
        if not self.enabled(source):
            raise SpatialForecastUnavailable(f"{SOURCES[source]['label']} is disabled (set {source}_ENABLED=true)")
        if source == "GFS":
            return GFSProvider()
        if source == "ECMWF":
            return ECMWFProvider()
        return ECMWFProvider(resolver=ECMWFProductResolver(model="aifs-single"), base_cache_dir=settings.AIFS_CACHE_DIR)

    def raw(self, source: str, variable: str, lead_hours: int, initialization: datetime) -> np.ndarray:
        key = (source, variable, lead_hours, utc_day(initialization))
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        try:
            forecast = self._provider(source).get_forecast(variable=variable, lead_hours=lead_hours, initialization=utc_day(initialization))
        except ValueError as error:
            raise SpatialForecastUnavailable(str(error)) from error
        values = np.asarray(forecast.values, dtype=float)
        with self._lock:
            self._cache[key] = values
            while len(self._cache) > self._capacity:
                self._cache.popitem(last=False)
        return values

    def field(self, source: str, variable: str, lead_hours: int, initialization: datetime) -> np.ndarray:
        if variable not in VARIABLES:
            raise SpatialForecastUnavailable(f"Unsupported variable: {variable}")
        if variable == "precipitation":
            if lead_hours <= 0:
                raise SpatialForecastUnavailable("Rainfall needs a lead time of at least 3 h")
            total = self.raw(source, "precipitation", lead_hours, initialization)
            if lead_hours > 24:
                total = total - self.raw(source, "precipitation", lead_hours - 24, initialization)
            return np.clip(total, 0.0, None)
        if variable == "tmax":
            if source == "AIFS":
                raise SpatialForecastUnavailable("AIFS open data does not publish maximum temperature")
            if lead_hours < 6:
                raise SpatialForecastUnavailable("Maximum temperature needs a lead time of at least 6 h")
            if source == "ECMWF":
                # IFS open data publishes 3 h maxima; combine two to match GFS's 6 h window.
                return np.maximum(self.raw(source, "tmax", lead_hours - 3, initialization),
                                  self.raw(source, "tmax", lead_hours, initialization))
        return self.raw(source, variable, lead_hours, initialization)

    def fields(self, variable: str, lead_hours: int, initialization: datetime) -> tuple[dict[str, np.ndarray], dict[str, str]]:
        """Every enabled source that can supply the field, plus the reason each missing one could not."""
        available: dict[str, np.ndarray] = {}
        missing: dict[str, str] = {}
        for source in SOURCES:
            if not self.enabled(source):
                missing[source] = "disabled"
                continue
            try:
                available[source] = self.field(source, variable, lead_hours, initialization)
            except SpatialForecastUnavailable as error:
                missing[source] = str(error)
        if not available:
            raise SpatialForecastUnavailable("No forecast source could supply this field: "
                                             + "; ".join(f"{source}: {reason}" for source, reason in missing.items()))
        return available, missing


STORE = FieldStore()


# --------------------------------------------------------------------------- cycles

_cycle_cache: dict[str, Any] = {"at": 0.0, "value": None}


def _exists(url: str) -> bool:
    try:
        with urlopen(Request(url, method="HEAD", headers={"User-Agent": "AIRAVAT/0.1"}), timeout=10) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def available_cycles(days: int = 5) -> list[dict[str, Any]]:
    """00Z cycles from the last few days with per-source availability (cached for 20 minutes)."""
    if _cycle_cache["value"] is not None and monotonic() - _cycle_cache["at"] < 1200:
        return _cycle_cache["value"]
    today = utc_day(datetime.now(timezone.utc))
    ecmwf_base = settings.ECMWF_BASE_URL.rstrip("/")
    cycles = []
    for offset in range(days):
        day = today - timedelta(days=offset)
        stamp = f"{day:%Y%m%d}"
        status = {
            "GFS": settings.GFS_ENABLED and _exists(
                f"{settings.GFS_BASE_URL.rstrip('/')}/pub/data/nccf/com/gfs/prod/gfs.{stamp}/00/atmos/gfs.t00z.pgrb2.0p25.f024.idx"),
            "ECMWF": settings.ECMWF_ENABLED and _exists(f"{ecmwf_base}/{stamp}/00z/ifs/0p25/oper/{stamp}000000-24h-oper-fc.index"),
            "AIFS": settings.AIFS_ENABLED and _exists(f"{ecmwf_base}/{stamp}/00z/aifs-single/0p25/oper/{stamp}000000-24h-oper-fc.index"),
        }
        cycles.append({"initialization": iso(day), "sources": status, "complete": status["GFS"] and status["ECMWF"]})
    _cycle_cache.update(at=monotonic(), value=cycles)
    return cycles


def latest_cycle() -> datetime:
    for cycle in available_cycles():
        if cycle["complete"]:
            return parse_iso(cycle["initialization"])
    raise SpatialForecastUnavailable("No 00Z cycle with both GFS and ECMWF IFS output is currently available")


# --------------------------------------------------------------------------- skill and weights

@dataclass
class SkillResult:
    variable: str
    lead_hours: int
    initialization: str
    sources: list[str]
    samples: list[dict[str, str]]
    skipped: list[dict[str, str]]
    evaluation: dict[str, Any]
    regions: list[dict[str, Any]]
    weights: dict[str, np.ndarray] = field(repr=False)
    mae: dict[str, np.ndarray] = field(repr=False)
    bias: dict[str, np.ndarray] = field(repr=False)
    computed_at: str = field(default_factory=lambda: iso(datetime.now(timezone.utc)))


_skill_cache: dict[tuple, SkillResult] = {}
_skill_locks: dict[tuple, Lock] = {}
_skill_guard = Lock()


def _smooth(values: np.ndarray) -> np.ndarray:
    return uniform_filter(values, size=SMOOTHING_CELLS, mode="nearest")


def _weights(errors: dict[str, np.ndarray], sample_count: int) -> dict[str, np.ndarray]:
    """Per-cell inverse-MAE weights over the sources, shrunk toward equal while the sample is small."""
    inverse = {source: 1.0 / np.maximum(_smooth(values), 1e-6) for source, values in errors.items()}
    total = sum(inverse.values())
    equal = 1.0 / len(errors)
    shrink = sample_count / (sample_count + SHRINKAGE_SAMPLES)
    return {source: equal + (value / total - equal) * shrink for source, value in inverse.items()}


def _learn(signed: dict[str, np.ndarray], days: list[int]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Bias (shrunk toward zero) and weights (from bias-corrected errors) using only the given sample days."""
    count = len(days)
    shrink = count / (count + SHRINKAGE_SAMPLES)
    bias = {source: _smooth(values[days].mean(axis=0)) * shrink for source, values in signed.items()}
    corrected = {source: np.abs(values[days] - bias[source]).mean(axis=0) for source, values in signed.items()}
    return bias, _weights(corrected, count)


def _skill_path(key: tuple) -> Path:
    variable, lead, init, window = key
    return SKILL_DIR / f"{variable}_{lead:03d}h_{init:%Y%m%d}_w{window}"


def _load_skill(key: tuple) -> SkillResult | None:
    path = _skill_path(key)
    meta, arrays = path.with_suffix(".json"), path.with_suffix(".npz")
    if not (meta.exists() and arrays.exists()):
        return None
    payload = json.loads(meta.read_text(encoding="utf-8"))
    with np.load(arrays) as data:
        payload["weights"] = {source: data[f"w_{source}"] for source in payload["sources"]}
        payload["mae"] = {source: data[f"m_{source}"] for source in payload["sources"]}
        payload["bias"] = {source: data[f"b_{source}"] for source in payload["sources"]}
    return SkillResult(**payload)


def _save_skill(key: tuple, result: SkillResult) -> None:
    path = _skill_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {name: value for name, value in asdict(result).items() if name not in {"weights", "mae", "bias"}}
    path.with_suffix(".json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    np.savez_compressed(path.with_suffix(".npz"),
                        **{f"w_{source}": value for source, value in result.weights.items()},
                        **{f"m_{source}": value for source, value in result.mae.items()},
                        **{f"b_{source}": value for source, value in result.bias.items()})


def compute_skill(variable: str, lead_hours: int, initialization: datetime, *, window_days: int = 7,
                  store: FieldStore = STORE) -> SkillResult:
    """Score every source over recent cycles and derive the per-cell weight maps.

    Weights are learned against the mean of the GFS and IFS 00 UTC analyses, which is
    neutral between the two analysis families. Scores are also reported against each
    analysis alone, because a model always looks best against its own analysis.
    """
    if not VARIABLES.get(variable, {}).get("verifiable"):
        raise SpatialForecastUnavailable(
            f"Skill-based weights are unavailable for {VARIABLES.get(variable, {}).get('label', variable)}: "
            "model analyses carry no reference for it (an observed reference such as ERA5 or IMD gridded data is required)")
    if lead_hours <= 0 or lead_hours % 24:
        raise SpatialForecastUnavailable("Skill scoring needs a 00 UTC valid time (lead a positive multiple of 24 h), where analyses exist")
    init = utc_day(initialization)
    key = (variable, lead_hours, init, window_days)
    with _skill_guard:
        if key in _skill_cache:
            return _skill_cache[key]
        lock = _skill_locks.setdefault(key, Lock())
    with lock:  # one computation per key; concurrent callers wait for it
        if key in _skill_cache:
            return _skill_cache[key]
        result = _load_skill(key) or _compute_skill(variable, lead_hours, init, window_days, store)
        _save_skill(key, result)
        with _skill_guard:
            _skill_cache[key] = result
        return result


def _compute_skill(variable: str, lead_hours: int, init: datetime, window_days: int, store: FieldStore) -> SkillResult:
    samples, skipped = [], []
    forecasts: list[dict[str, np.ndarray]] = []
    analyses: list[dict[str, np.ndarray]] = []
    for offset in range(1, window_days + 1):
        start = init - timedelta(days=offset)
        valid = start + timedelta(hours=lead_hours)
        if valid > init:
            continue
        try:
            day_analyses = {source: store.field(source, variable, 0, valid) for source in ANALYSIS_SOURCES}
            day_forecasts, missing = store.fields(variable, lead_hours, start)
        except SpatialForecastUnavailable as error:
            skipped.append({"initialization": iso(start), "reason": str(error)})
            continue
        # A day missing an enabled model would shrink the weighted set for every other day, so skip it.
        absent = {source: reason for source, reason in missing.items() if reason != "disabled"}
        if absent:
            skipped.append({"initialization": iso(start),
                            "reason": "; ".join(f"{source}: {reason}" for source, reason in absent.items())})
            continue
        samples.append({"initialization": iso(start), "valid_time": iso(valid), "sources": sorted(day_forecasts)})
        forecasts.append(day_forecasts)
        analyses.append(day_analyses)
    if not samples:
        raise SpatialForecastUnavailable(
            f"No past cycle for a {lead_hours} h lead has forecasts and verifying analyses retrievable "
            "(ECMWF open data keeps about four days)")
    # Only sources present on every sample day can be weighted consistently.
    sources = [source for source in SOURCES if all(source in day for day in forecasts)]
    count = len(samples)
    references = {
        "mean": [(day["GFS"] + day["ECMWF"]) / 2.0 for day in analyses],
        "GFS": [day["GFS"] for day in analyses],
        "ECMWF": [day["ECMWF"] for day in analyses],
    }
    signed = {source: np.stack([day[source] - truth for day, truth in zip(forecasts, references["mean"])]) for source in sources}
    errors = {source: np.abs(values) for source, values in signed.items()}
    bias, weights = _learn(signed, list(range(count)))
    india = india_mask()

    # Leave-one-out: each day is corrected and blended with bias and weights learned only from the other days.
    scores: dict[str, dict[str, list[float]]] = {name: {} for name in references}
    for index in range(count):
        others = [other for other in range(count) if other != index] or [index]
        day_bias, day_weights = _learn(signed, others)
        raw_weights = _weights({source: values[others].mean(axis=0) for source, values in errors.items()}, len(others))
        candidates = {source: forecasts[index][source] for source in sources}
        candidates["equal"] = sum(candidates[source] for source in sources) / len(sources)
        candidates["weights_only"] = sum(raw_weights[source] * forecasts[index][source] for source in sources)
        candidates["adaptive"] = sum(day_weights[source] * (forecasts[index][source] - day_bias[source]) for source in sources)
        for reference, truths in references.items():
            for name, values in candidates.items():
                scores[reference].setdefault(name, []).append(float(np.abs(values - truths[index])[india].mean()))
    table = {reference: {name: float(np.mean(values)) for name, values in methods.items()} for reference, methods in scores.items()}
    mean_table = table["mean"]
    evaluation = {
        "method": "leave-one-out" if count > 1 else "in-sample (single cycle; not an independent test)",
        "reference": "mean of GFS and IFS 00 UTC analyses (model analyses, not observations)",
        "units": VARIABLES[variable]["units"],
        "mae": mean_table,
        "by_reference": table,
        "adaptive_vs_equal_pct": (mean_table["equal"] - mean_table["adaptive"]) / mean_table["equal"] * 100 if mean_table["equal"] > 0 else 0.0,
        "methods": {"equal": "equal-weight mean", "weights_only": "skill weights, no bias correction",
                    "adaptive": "AIRAVAT: per-cell bias correction + skill weights"},
        "caveat": ("Each model scores best against its own analysis and any blend scores well against their mean, "
                   "so blend-versus-single-model gains here are not proof of better skill; "
                   "that needs an independent reference such as ERA5 or station observations. "
                   "Adaptive-versus-equal is a like-for-like comparison."),
    }
    mae_fields = {source: values.mean(axis=0) for source, values in errors.items()}
    regions = []
    for key_name, label in REGIONS:
        mask = region_masks()[key_name]
        if not mask.any():
            continue
        region_mae = {source: float(mae_fields[source][mask].mean()) for source in sources}
        regions.append({
            "region": key_name, "label": label, "mae": region_mae,
            "weights": {source: float(weights[source][mask].mean()) for source in sources},
            "bias": {source: float(bias[source][mask].mean()) for source in sources},
            "favoured": min(region_mae, key=region_mae.__getitem__),
        })
    return SkillResult(variable, lead_hours, iso(init), sources, samples, skipped, evaluation, regions, weights, mae_fields, bias)


def skill_summary(result: SkillResult) -> dict[str, Any]:
    india = india_mask()
    stacked = np.stack([result.weights[source] for source in result.sources])
    dominant = stacked.argmax(axis=0)
    return {
        "status": "AVAILABLE",
        "variable": result.variable,
        "lead_hours": result.lead_hours,
        "initialization": result.initialization,
        "sources": result.sources,
        "sample_count": len(result.samples),
        "samples": result.samples,
        "skipped": result.skipped,
        "shrinkage": {"prior": "equal weights", "pseudo_samples": SHRINKAGE_SAMPLES},
        "smoothing": f"{SMOOTHING_CELLS}×{SMOOTHING_CELLS} cell box (±1°)",
        "evaluation": result.evaluation,
        "regions": result.regions,
        "domain": {
            "mean_weight": {source: float(result.weights[source][india].mean()) for source in result.sources},
            "mean_bias": {source: float(result.bias[source][india].mean()) for source in result.sources},
            "favoured_area_pct": {source: float((dominant[india] == index).mean() * 100) for index, source in enumerate(result.sources)},
        },
        "computed_at": result.computed_at,
    }


# --------------------------------------------------------------------------- map layers

def blend(variable: str, lead_hours: int, initialization: datetime, weighting: str,
          store: FieldStore = STORE) -> tuple[np.ndarray, dict[str, Any]]:
    available, missing = store.fields(variable, lead_hours, initialization)
    india = india_mask()
    if weighting == "adaptive":
        skill = compute_skill(variable, lead_hours, initialization, store=store)
        sources = [source for source in skill.sources if source in available]
        if not sources:
            raise SpatialForecastUnavailable("None of the skill-scored sources is available for this cycle")
        total = sum(skill.weights[source] for source in sources)
        weights = {source: skill.weights[source] / total for source in sources}
        available = {source: available[source] - skill.bias[source] for source in sources}
        provenance = {
            "weight_policy": "skill-adaptive: per-cell bias correction, then inverse regional MAE weights (both shrunk toward the prior)",
            "bias_correction": {source: float(skill.bias[source][india].mean()) for source in sources},
            "skill_samples": len(skill.samples),
            "skill_reference": skill.evaluation["reference"],
        }
    elif weighting == "equal":
        sources = list(available)
        weights = {source: np.full(available[source].shape, 1.0 / len(sources)) for source in sources}
        provenance = {"weight_policy": "equal-weight baseline"}
    else:
        raise SpatialForecastUnavailable(f"Unknown weighting: {weighting}")
    values = sum(weights[source] * available[source] for source in sources)
    return values, {
        "blend_method": "per-cell weighted mean",
        **provenance,
        "source_weights": {source: float(weights[source][india].mean()) for source in sources},
        "weights_are": "India-mean of the per-cell weight maps" if weighting == "adaptive" else "uniform",
        "missing_sources": missing,
    }


def layer(variable: str, lead_hours: int, initialization: datetime, name: str, weighting: str = "adaptive",
          source: str | None = None, store: FieldStore = STORE) -> tuple[np.ndarray, dict[str, Any]]:
    """Return (values, provenance) for one map layer."""
    init = utc_day(initialization)
    base = {
        "variable": variable, "variable_label": VARIABLES[variable]["label"], "variable_note": VARIABLES[variable]["note"],
        "initialization": iso(init), "lead_hours": lead_hours, "valid_time": iso(init + timedelta(hours=lead_hours)),
    }
    if name in SOURCES:
        return store.field(name, variable, lead_hours, init), {**base, "layer": name, "model": SOURCES[name]["model"],
                                                               "source_label": SOURCES[name]["label"], "kind": SOURCES[name]["kind"]}
    if name == "blend":
        values, provenance = blend(variable, lead_hours, init, weighting, store)
        return values, {**base, **provenance, "layer": "blend", "model": "AIRAVAT", "weighting": weighting}
    if name == "spread":
        available, missing = store.fields(variable, lead_hours, init)
        if len(available) < 2:
            raise SpatialForecastUnavailable("Model spread needs at least two sources")
        stacked = np.stack(list(available.values()))
        return stacked.max(axis=0) - stacked.min(axis=0), {
            **base, "layer": "spread", "model": "Model spread", "definition": "max − min across sources per cell",
            "source_models": sorted(available), "missing_sources": missing}
    if name == "weights":
        skill = compute_skill(variable, lead_hours, init, store=store)
        selected = source or skill.sources[0]
        if selected not in skill.weights:
            raise SpatialForecastUnavailable(f"No weight map for {selected}")
        return skill.weights[selected], {
            **base, "layer": "weights", "model": f"{SOURCES[selected]['label']} weight", "weight_source": selected,
            "definition": f"Weight given to {SOURCES[selected]['label']} per cell (weights sum to 1 across {', '.join(skill.sources)})",
            "skill_samples": len(skill.samples)}
    raise SpatialForecastUnavailable(f"Unknown layer: {name}")


def layer_units(variable: str, name: str) -> str:
    return "weight" if name == "weights" else VARIABLES[variable]["units"]


def field_response(values: np.ndarray, provenance: dict[str, Any], units: str) -> dict[str, Any]:
    inside = values[india_mask()]
    return {
        "status": "AVAILABLE",
        "source": provenance.get("layer"),
        "model": provenance.get("model"),
        "variable": provenance["variable"],
        "lead_hours": provenance["lead_hours"],
        "initialization": provenance["initialization"],
        "units": units,
        "grid_spec": GRID_SPEC.model_dump(),
        "latitudes": LATITUDES.round(4).tolist(),
        "longitudes": LONGITUDES.round(4).tolist(),
        "values": np.round(values, 3).tolist(),
        "summary": {"india_min": float(inside.min()), "india_max": float(inside.max()), "india_mean": float(inside.mean())},
        "provenance": provenance,
    }


# --------------------------------------------------------------------------- extreme weather guidance

def hazard_lead(hazard: str, day: int) -> int:
    """Lead for forecast day ``day`` (0 = the initialization date)."""
    if hazard == "heavy_rain":
        return 24 * day + 24  # rainfall over 00–24 UTC of that date
    return 24 * day + 12  # 12 UTC ≈ 17:30 IST, the afternoon peak for heat and wind


def _hotspots(values: np.ndarray, threshold: float, limit: int = 5) -> list[dict[str, float]]:
    india = india_mask()
    candidates = sorted(np.argwhere(india & (values >= threshold)).tolist(), key=lambda cell: -values[cell[0], cell[1]])
    spots: list[dict[str, float]] = []
    for row, column in candidates:
        latitude, longitude = float(LATITUDES[row]), float(LONGITUDES[column])
        if all(abs(latitude - spot["latitude"]) > 1.5 or abs(longitude - spot["longitude"]) > 1.5 for spot in spots):
            spots.append({"latitude": latitude, "longitude": longitude, "value": float(values[row, column])})
        if len(spots) == limit:
            break
    return spots


def extremes(initialization: datetime, day: int, store: FieldStore = STORE) -> dict[str, Any]:
    india = india_mask()
    area = cell_area_km2()
    init = utc_day(initialization)
    result: dict[str, Any] = {"initialization": iso(init), "day": day,
                              "date": f"{init + timedelta(days=day):%Y-%m-%d}", "hazards": []}
    for key, hazard in HAZARDS.items():
        lead = hazard_lead(key, day)
        entry: dict[str, Any] = {"hazard": key, "label": hazard["label"], "variable": hazard["variable"],
                                 "units": hazard["units"], "lead_hours": lead,
                                 "valid_time": iso(init + timedelta(hours=lead))}
        try:
            available, missing = store.fields(hazard["variable"], lead, init)
        except SpatialForecastUnavailable as error:
            result["hazards"].append({**entry, "status": "UNAVAILABLE", "reason": str(error)})
            continue
        blended = sum(available.values()) / len(available)
        first = hazard["levels"][0][0]
        levels = []
        for threshold, label in hazard["levels"]:
            exceed = india & (blended >= threshold)
            levels.append({"label": label, "threshold": threshold, "area_km2": float(area[exceed].sum()), "cells": int(exceed.sum())})
        exceed_count = sum((values >= first).astype(int) for values in available.values())
        peak = np.unravel_index(np.where(india, blended, -np.inf).argmax(), blended.shape)
        entry.update({
            "status": "AVAILABLE",
            "sources": sorted(available),
            "missing_sources": missing,
            "levels": levels,
            "highest_level": next((label for threshold, label in reversed(hazard["levels"]) if blended[peak] >= threshold), None),
            "peak": {"value": float(blended[peak]), "latitude": float(LATITUDES[peak[0]]), "longitude": float(LONGITUDES[peak[1]]),
                     "by_source": {source: float(values[peak]) for source, values in available.items()}},
            "agreement": {
                "threshold": first,
                "all_models_km2": float(area[india & (exceed_count == len(available))].sum()),
                "some_models_km2": float(area[india & (exceed_count > 0) & (exceed_count < len(available))].sum()),
                "model_count": len(available),
                # A lone model crossing the threshold is a watch signal the blend alone would hide.
                "by_source_km2": {source: float(area[india & (values >= first)].sum()) for source, values in available.items()},
            },
            "hotspots": _hotspots(blended, first),
            "blend": f"equal-weight mean of {', '.join(sorted(available))}",
        })
        result["hazards"].append(entry)
    return result


def hazard_field(initialization: datetime, day: int, hazard: str, store: FieldStore = STORE) -> tuple[np.ndarray, dict[str, Any]]:
    if hazard not in HAZARDS:
        raise SpatialForecastUnavailable(f"Unknown hazard: {hazard}")
    spec = HAZARDS[hazard]
    values, provenance = layer(spec["variable"], hazard_lead(hazard, day), initialization, "blend", "equal", store=store)
    return values, {**provenance, "hazard": hazard, "thresholds": [{"value": value, "label": label} for value, label in spec["levels"]]}


# --------------------------------------------------------------------------- persistence for the operational run

def write_product(initialization: datetime, name: str, payload: dict[str, Any]) -> Path:
    directory = PRODUCTS_DIR / f"{utc_day(initialization):%Y%m%d}T00Z"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- per-cell explanation

def point(variable: str, lead_hours: int, initialization: datetime, latitude: float, longitude: float,
          store: FieldStore = STORE) -> dict[str, Any]:
    """How the blend at one grid cell is built: each source's value, bias correction, weight and contribution."""
    if not (GRID_SPEC.south <= latitude <= GRID_SPEC.north and GRID_SPEC.west <= longitude <= GRID_SPEC.east):
        raise SpatialForecastUnavailable("Point is outside the AIRAVAT domain")
    row = int(round((latitude - GRID_SPEC.south) / GRID_SPEC.resolution))
    column = int(round((longitude - GRID_SPEC.west) / GRID_SPEC.resolution))
    init = utc_day(initialization)
    available, missing = store.fields(variable, lead_hours, init)
    skill, skill_reason = None, None
    try:
        skill = compute_skill(variable, lead_hours, init, store=store)
    except SpatialForecastUnavailable as error:
        skill_reason = str(error)
    weighted = [source for source in (skill.sources if skill else []) if source in available]
    total = sum(skill.weights[source][row, column] for source in weighted) if weighted else 0.0
    sources = []
    for source, values in available.items():
        value = float(values[row, column])
        entry: dict[str, Any] = {"source": source, **SOURCES[source], "value": value}
        if source in weighted:
            bias = float(skill.bias[source][row, column])
            weight = float(skill.weights[source][row, column] / total)
            entry.update(bias=bias, corrected=value - bias, weight=weight, contribution=weight * (value - bias),
                         regional_mae=float(skill.mae[source][row, column]))
        sources.append(entry)
    values_here = [entry["value"] for entry in sources]
    region = next((label for key, label in REGIONS if region_masks()[key][row, column]), None)
    return {
        "status": "AVAILABLE",
        "variable": variable, "units": VARIABLES[variable]["units"], "lead_hours": lead_hours,
        "initialization": iso(init), "valid_time": iso(init + timedelta(hours=lead_hours)),
        "latitude": float(LATITUDES[row]), "longitude": float(LONGITUDES[column]),
        "inside_india": bool(india_mask()[row, column]), "region": region,
        "sources": sources, "missing_sources": missing,
        "equal_blend": float(np.mean(values_here)),
        "adaptive_blend": float(sum(entry["contribution"] for entry in sources if "contribution" in entry)) if weighted else None,
        "spread": float(max(values_here) - min(values_here)) if len(values_here) > 1 else 0.0,
        "skill_reason": skill_reason,
        "skill_samples": len(skill.samples) if skill else 0,
    }
