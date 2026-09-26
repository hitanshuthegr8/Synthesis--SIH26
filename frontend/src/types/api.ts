export type Forecast = {
  model_id: string;
  variable: string;
  latitude: number;
  longitude: number;
  initialization_time: string;
  lead_hours: number;
  value: number;
  unit: string;
};

export type Disagreement = {
  mean: number;
  std: number;
  min_value: number;
  max_value: number;
  range: number;
  level: string;
  model_count: number;
};

export type Blend = {
  variable: string;
  latitude: number;
  longitude: number;
  valid_time: string;
  blended_value: number;
  lower_bound: number;
  upper_bound: number;
  model_weights: Record<string, number>;
  disagreement: Disagreement;
  regime: string;
  regime_confidence: number;
  explanation: string[];
  fallback_mode: boolean;
  run_id: string;
  cycle_time: string;
  algorithm_version: string;
  dataset_version: string;
  config_hash: string;
  source_availability: Record<string, string>;
};

export type ReliabilityEstimate = {
  model_id: string;
  variable: string;
  lead_hours: number;
  mae: number;
  sample_count: number;
  reliability: number;
  sufficient_samples: boolean;
};

export type ModelSkill = {
  model_id: string;
  variable: string;
  region: string;
  lead_hours: number;
  season: string | null;
  regime: string | null;
  metric: string;
  score: number;
  sample_count: number;
};

export type Verification = {
  run_id: string;
  variable: string;
  latitude: number;
  longitude: number;
  valid_time: string;
  forecast_value: number;
  observation_value: number;
  error: number;
  absolute_error: number;
  model_errors: Record<string, number>;
  regime: string;
  lead_hours: number;
};

export type PipelineStage = {
  name: string;
  status: string;
  record_count?: number;
  regime?: string;
  level?: string;
};

export type ComputationTrace = {
  run_id: string;
  created_at: string;
  stages: PipelineStage[];
  provenance: {
    algorithm_version: string;
    dataset_version: string;
    config_hash: string;
    random_seed: number;
    demo_mode: boolean;
  };
};

export type SourceStatus = {
  source: string;
  status: string;
  mode: string;
};

export type Health = {
  status: string;
  version: string;
  demo_mode: boolean;
};

export type Dossier = {
  run: Blend;
  inputs: Forecast[];
  verification: Verification;
  computation_trace: ComputationTrace;
};

export type GridSpec = {
  south: number;
  north: number;
  west: number;
  east: number;
  resolution: number;
  latitude_count: number;
  longitude_count: number;
};

export type SpatialFieldResponse = {
  status: "AVAILABLE" | "UNAVAILABLE";
  source?: string | null;
  model?: string | null;
  variable?: string;
  lead_hours?: number;
  initialization?: string | null;
  units?: string;
  grid_spec?: GridSpec;
  latitudes?: number[];
  longitudes?: number[];
  values?: number[][] | null;
  provenance?: Record<string, unknown>;
  reason?: string;
};

export type SpatialVerificationResponse = {
  status: "AVAILABLE" | "UNAVAILABLE";
  metrics?: {
    mae: number;
    rmse: number;
    bias: number;
    valid_cell_count: number;
    total_cell_count: number;
    invalid_cell_count: number;
  } | null;
  absolute_error_field?: number[][] | null;
  provenance?: Record<string, unknown>;
  reason?: string;
};
