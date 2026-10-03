import type { Blend, Forecast, SpatialFieldResponse, Verification } from "./api";

export type SourceId = "GFS" | "ECMWF" | "AIFS";
export type VariableId = "temperature" | "tmax" | "precipitation" | "wind_speed";
export type LayerId = "blend" | SourceId | "spread" | "weights";
export type Weighting = "adaptive" | "equal";

export type Cycle = { initialization: string; sources: Record<SourceId, boolean>; complete: boolean };

export type CatalogSource = { id: SourceId; label: string; model: string; kind: string; centre: string; enabled: boolean };
export type CatalogVariable = { id: VariableId; label: string; units: string; verifiable: boolean; note: string };
export type CatalogHazard = { id: string; label: string; variable: VariableId; units: string; levels: { threshold: number; label: string }[] };

export type Catalog = {
  sources: CatalogSource[];
  variables: CatalogVariable[];
  layers: LayerId[];
  hazards: CatalogHazard[];
  regions: { id: string; label: string }[];
  cycles: Cycle[];
  era5_enabled: boolean;
};

export type SynthesisField = SpatialFieldResponse & {
  summary?: { india_min: number; india_max: number; india_mean: number };
};

export type SkillSummary = {
  status: "AVAILABLE" | "UNAVAILABLE";
  reason?: string;
  variable: VariableId;
  lead_hours: number;
  initialization?: string;
  sources: SourceId[];
  sample_count: number;
  samples: { initialization: string; valid_time: string; sources: SourceId[] }[];
  skipped: { initialization: string; reason: string }[];
  shrinkage: { prior: string; pseudo_samples: number };
  smoothing: string;
  evaluation: {
    method: string;
    reference: string;
    units: string;
    mae: Record<string, number>;
    by_reference: Record<"mean" | "GFS" | "ECMWF", Record<string, number>>;
    adaptive_vs_equal_pct: number;
    methods: Record<string, string>;
    caveat: string;
  };
  regions: {
    region: string;
    label: string;
    mae: Record<SourceId, number>;
    weights: Record<SourceId, number>;
    bias: Record<SourceId, number>;
    favoured: SourceId;
  }[];
  domain: {
    mean_weight: Record<SourceId, number>;
    mean_bias: Record<SourceId, number>;
    favoured_area_pct: Record<SourceId, number>;
  };
  computed_at: string;
};

export type HazardLevel = { label: string; threshold: number; area_km2: number; cells: number };

export type Hazard = {
  hazard: "heavy_rain" | "heat" | "high_wind";
  label: string;
  variable: VariableId;
  units: string;
  lead_hours: number;
  valid_time: string;
  status: "AVAILABLE" | "UNAVAILABLE";
  reason?: string;
  sources?: SourceId[];
  missing_sources?: Record<string, string>;
  levels?: HazardLevel[];
  highest_level?: string | null;
  peak?: { value: number; latitude: number; longitude: number; by_source: Partial<Record<SourceId, number>> };
  agreement?: { threshold: number; all_models_km2: number; some_models_km2: number; model_count: number; by_source_km2?: Partial<Record<SourceId, number>> };
  hotspots?: { latitude: number; longitude: number; value: number }[];
  blend?: string;
};

export type Extremes = {
  status: "AVAILABLE" | "UNAVAILABLE";
  reason?: string;
  initialization?: string;
  day: number;
  date?: string;
  hazards?: Hazard[];
};

export type PointSource = {
  source: SourceId;
  label: string;
  model: string;
  kind: string;
  value: number;
  bias?: number;
  corrected?: number;
  weight?: number;
  contribution?: number;
  regional_mae?: number;
};

export type PointExplanation = {
  status: "AVAILABLE" | "UNAVAILABLE";
  reason?: string;
  variable: VariableId;
  units: string;
  lead_hours: number;
  valid_time: string;
  latitude: number;
  longitude: number;
  inside_india: boolean;
  region: string | null;
  sources: PointSource[];
  missing_sources: Record<string, string>;
  equal_blend: number;
  adaptive_blend: number | null;
  spread: number;
  skill_reason: string | null;
  skill_samples: number;
};

export type RunLogEntry = { time: string; stage: string; status: "complete" | "unavailable" | "failed" | "warning"; message: string };

export type OperationalRun = {
  run_id: string;
  initialization: string;
  variables: VariableId[];
  leads: number[];
  days: number[];
  status: "queued" | "running" | "complete" | "complete_with_issues" | "failed" | "interrupted";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  total_steps: number;
  completed_steps: number;
  log: RunLogEntry[];
  products: { name: string; path: string; weighting?: string; adaptive_vs_equal_pct?: number | null; skill_samples?: number; sources?: string[]; flags?: string[]; watch?: string[] }[];
};

export type PipelineScenario = "normal" | "heavy_rain" | "model_conflict" | "model_disagreement" | "model_failure";
export type PipelineSource = "ecmwf" | "gfs" | "gefs" | "ai";

/** Response of POST /api/pipeline/run (forecast-cycle pipeline on a synthetic benchmark point). */
export type PipelineRun = {
  run_id: string;
  status: string;
  blend: Pick<Blend, "variable" | "blended_value" | "lower_bound" | "upper_bound" | "model_weights" | "disagreement" | "regime" | "regime_confidence" | "explanation" | "fallback_mode" | "run_id" | "dataset_version"> & {
    algorithm: string;
    processing_time_ms: number;
    region: string;
    configuration_hash: string;
  };
  forecasts: Forecast[];
  verification: Verification;
  autopsy: { assessment: string; blend_error: number; model_forecasts: Record<string, number>; model_errors: Record<string, number> };
  trace: {
    scenario: string;
    status: string;
    duration_ms: number;
    algorithm_version: string;
    dataset_version: string;
    configuration_hash: string;
    stale_from_run_id: string | null;
    source_availability: Record<string, boolean>;
    steps: { name: string; status: string; duration_ms: number; details: string[] }[];
  };
};
