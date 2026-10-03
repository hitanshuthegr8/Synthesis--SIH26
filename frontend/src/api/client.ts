import type {
  Blend,
  ComputationTrace,
  Dossier,
  Forecast,
  Health,
  ModelSkill,
  ReliabilityEstimate,
  SpatialFieldResponse,
  SpatialVerificationResponse,
  SourceStatus,
  Verification,
} from "../types/api";
import type {
  Catalog,
  Extremes,
  LayerId,
  OperationalRun,
  PipelineRun,
  PipelineScenario,
  PipelineSource,
  PointExplanation,
  SkillSummary,
  SourceId,
  SynthesisField,
  VariableId,
  Weighting,
} from "../types/synthesis";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export type LoadingState<T> =
  | { status: "idle" | "loading"; data: null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: null; error: ApiError };

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const defaultTimeoutMs = 10_000;
// Spatial endpoints download and decode GRIB files from NOAA/ECMWF on a cold cache.
const spatialTimeoutMs = 120_000;

async function get<T>(path: string, timeoutMs = defaultTimeoutMs): Promise<T> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new ApiError(`Request failed with status ${response.status}.`, response.status);
    }
    try {
      return await response.json() as T;
    } catch {
      throw new ApiError("The forecast service returned invalid JSON.", response.status);
    }
  } catch (caught) {
    if (caught instanceof ApiError) throw caught;
    if (caught instanceof DOMException && caught.name === "AbortError") {
      throw new ApiError(`Request timed out after ${timeoutMs} ms.`);
    }
    throw new ApiError(caught instanceof Error ? caught.message : "Unable to reach the forecast service.");
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

async function post<T>(path: string, timeoutMs = defaultTimeoutMs, body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method: "POST",
      headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {
      const detail = await response.json().then((payload: { detail?: unknown }) => payload.detail).catch(() => undefined);
      const nested = (detail as { error?: { message?: unknown } } | undefined)?.error?.message;
      const message = typeof detail === "string" ? detail : typeof nested === "string" ? nested : `Request failed with status ${response.status}.`;
      throw new ApiError(message, response.status);
    }
    return await response.json() as T;
  } catch (caught) {
    if (caught instanceof ApiError) throw caught;
    if (caught instanceof DOMException && caught.name === "AbortError") throw new ApiError(`Request timed out after ${timeoutMs} ms.`);
    throw new ApiError(caught instanceof Error ? caught.message : "Unable to reach the forecast service.");
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export const api = {
  getHealth: () => get<Health>("/api/health"),
  getSources: () => get<SourceStatus[]>("/api/sources"),
  getForecasts: (variable = "temperature", leadHours = 24, scenario?: string) =>
    get<Forecast[]>(`/api/forecasts?${query({ variable, lead_hours: leadHours, scenario })}`),
  getForecast: (runId: string) => get<Blend>(`/api/forecast/${encodeURIComponent(runId)}`),
  getComputationTrace: (runId: string) => get<ComputationTrace>(`/api/computation/${encodeURIComponent(runId)}`),
  getReliability: (variable = "temperature", leadHours = 24, scenario?: string) =>
    get<ModelSkill[]>(`/api/reliability?${query({ variable, lead_hours: leadHours, scenario })}`),
  getModelReliability: (variable = "temperature", leadHours = 24, scenario?: string) =>
    get<ReliabilityEstimate[]>(`/api/reliability/model?${query({ variable, lead_hours: leadHours, scenario })}`),
  getVerification: (variable = "temperature", leadHours = 24, scenario?: string) =>
    get<Verification>(`/api/verification?${query({ variable, lead_hours: leadHours, scenario })}`),
  getAutopsy: (runId: string) => get<Verification>(`/api/autopsy/${encodeURIComponent(runId)}`),
  getDossier: (runId: string) => get<Dossier>(`/api/runs/${encodeURIComponent(runId)}/dossier`),
  getSpatialForecast: (source: "GFS" | "ECMWF", model: "GFS" | "IFS", variable: string, leadHours: number, initialization: string) =>
    get<SpatialFieldResponse>(`/api/forecast/grid?${query({ source, model, variable, lead_hours: leadHours, initialization })}`, spatialTimeoutMs),
  getSpatialBlend: (variable: string, leadHours: number, initialization: string) =>
    get<SpatialFieldResponse>(`/api/forecast/grid/blend?${query({ variable, lead_hours: leadHours, initialization })}`, spatialTimeoutMs),
  verifySpatialForecast: (source: "GFS" | "ECMWF", model: "GFS" | "IFS", variable: string, leadHours: number, initialization: string) =>
    post<SpatialVerificationResponse>(`/api/forecast/verification/spatial?${query({ source, model, variable, lead_hours: leadHours, initialization })}`, spatialTimeoutMs),
};

// Live model fields: a cold cycle downloads and decodes GRIB from three centres, and skill scoring
// replays several past cycles, so the first request can take a minute or more.
const liveTimeoutMs = 240_000;

export const synthesis = {
  catalog: () => get<Catalog>("/api/synthesis/catalog", 30_000),
  field: (params: { variable: VariableId; lead: number; layer: LayerId; weighting: Weighting; source?: SourceId; initialization?: string }) =>
    get<SynthesisField>(`/api/synthesis/field?${query({ variable: params.variable, lead_hours: params.lead, layer: params.layer, weighting: params.weighting, source: params.source, initialization: params.initialization })}`, liveTimeoutMs),
  skill: (variable: VariableId, lead: number, initialization?: string) =>
    get<SkillSummary>(`/api/synthesis/skill?${query({ variable, lead_hours: lead, initialization })}`, liveTimeoutMs),
  point: (variable: VariableId, lead: number, latitude: number, longitude: number, initialization?: string) =>
    get<PointExplanation>(`/api/synthesis/point?${query({ variable, lead_hours: lead, latitude, longitude, initialization })}`, liveTimeoutMs),
  extremes: (day: number, initialization?: string) =>
    get<Extremes>(`/api/synthesis/extremes?${query({ day, initialization })}`, liveTimeoutMs),
  extremeField: (hazard: string, day: number, initialization?: string) =>
    get<SynthesisField>(`/api/synthesis/extremes/field?${query({ hazard, day, initialization })}`, liveTimeoutMs),
  runs: () => get<OperationalRun[]>("/api/synthesis/runs"),
  run: (runId: string) => get<OperationalRun>(`/api/synthesis/runs/${encodeURIComponent(runId)}`),
  startRun: (body: { initialization?: string; variables: VariableId[]; leads: number[]; days: number[] }) =>
    post<OperationalRun>("/api/synthesis/runs", 30_000, body),
  pipeline: (scenario: PipelineScenario, lead: number, unavailable: PipelineSource[] = []) =>
    post<PipelineRun>("/api/pipeline/run", 30_000, { scenario, lead_hours: lead, unavailable_sources: unavailable }),
};

function query(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return params.toString();
}
