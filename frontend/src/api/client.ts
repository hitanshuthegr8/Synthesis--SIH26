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

async function post<T>(path: string, timeoutMs = defaultTimeoutMs): Promise<T> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method: "POST",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) throw new ApiError(`Request failed with status ${response.status}.`, response.status);
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
    get<SpatialFieldResponse>(`/api/forecast/grid?${query({ source, model, variable, lead_hours: leadHours, initialization })}`),
  getSpatialBlend: (variable: string, leadHours: number, initialization: string) =>
    get<SpatialFieldResponse>(`/api/forecast/grid/blend?${query({ variable, lead_hours: leadHours, initialization })}`),
  verifySpatialForecast: (source: "GFS" | "ECMWF", model: "GFS" | "IFS", variable: string, leadHours: number, initialization: string) =>
    post<SpatialVerificationResponse>(`/api/forecast/verification/spatial?${query({ source, model, variable, lead_hours: leadHours, initialization })}`),
};

function query(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return params.toString();
}
