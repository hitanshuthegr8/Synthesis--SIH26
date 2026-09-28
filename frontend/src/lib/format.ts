import type { SourceId, VariableId } from "../types/synthesis";

export const SOURCE_ORDER: SourceId[] = ["GFS", "ECMWF", "AIFS"];

export const SOURCE_META: Record<SourceId, { label: string; short: string; kind: string; color: string }> = {
  GFS: { label: "NOAA GFS", short: "GFS", kind: "Physics NWP", color: "var(--series-gfs)" },
  ECMWF: { label: "ECMWF IFS", short: "IFS", kind: "Physics NWP", color: "var(--series-ifs)" },
  AIFS: { label: "ECMWF AIFS", short: "AIFS", kind: "AI / ML", color: "var(--series-aifs)" },
};

export const VARIABLE_META: Record<VariableId, { label: string; short: string; units: string; leads: number[]; palette: "thermal" | "rain" | "wind"; scale: "quantile" | "linear" }> = {
  temperature: { label: "2 m temperature", short: "Temperature", units: "C", leads: [24, 48, 72, 96, 120], palette: "thermal", scale: "quantile" },
  tmax: { label: "Afternoon max temperature", short: "Max temp", units: "C", leads: [12, 36, 60, 84, 108], palette: "thermal", scale: "quantile" },
  precipitation: { label: "24 h rainfall", short: "Rainfall", units: "mm", leads: [24, 48, 72, 96, 120], palette: "rain", scale: "linear" },
  wind_speed: { label: "10 m wind speed", short: "Wind", units: "m/s", leads: [24, 48, 72, 96, 120], palette: "wind", scale: "linear" },
};

export function unitLabel(units: string): string {
  return units === "C" ? "°C" : units;
}

export function number(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || !Number.isFinite(value) ? "—" : value.toFixed(digits);
}

export function signed(value: number, digits = 1): string {
  return `${value > 0 ? "+" : value < 0 ? "−" : "±"}${Math.abs(value).toFixed(digits)}`;
}

export function percent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function area(km2: number): string {
  if (km2 >= 1e5) return `${(km2 / 1e5).toFixed(1)} lakh km²`;
  if (km2 >= 1000) return `${Math.round(km2 / 1000).toLocaleString("en-IN")}k km²`;
  return `${Math.round(km2).toLocaleString("en-IN")} km²`;
}

const dateFormat = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
const istFormat = new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });

export function cycleLabel(iso: string | undefined): string {
  return iso ? `${dateFormat.format(new Date(iso))} · 00 UTC` : "—";
}

export function validLabel(initialization: string | undefined, lead: number): string {
  if (!initialization) return `+${lead} h`;
  const valid = new Date(new Date(initialization).getTime() + lead * 3_600_000);
  return `${istFormat.format(valid)} IST`;
}

export function istTime(iso: string | null | undefined): string {
  return iso ? `${istFormat.format(new Date(iso))} IST` : "—";
}

/** Sources that alone flag an area the blend keeps below threshold, e.g. "GFS alone flags 9k km²". */
export function watchSignal(agreement: { all_models_km2: number; some_models_km2: number; by_source_km2?: Partial<Record<SourceId, number>> } | undefined): string | null {
  if (!agreement || agreement.some_models_km2 <= 0) return null;
  const flagged = SOURCE_ORDER.filter((source) => (agreement.by_source_km2?.[source] ?? 0) > 0);
  const names = flagged.map((source) => SOURCE_META[source].short).join(" + ") || "Some models";
  return `${names} ${flagged.length === 1 ? "alone flags" : "flag"} ${area(agreement.some_models_km2)}`;
}

export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

export function coordinate(latitude: number, longitude: number): string {
  return `${latitude.toFixed(2)}°N ${longitude.toFixed(2)}°E`;
}
