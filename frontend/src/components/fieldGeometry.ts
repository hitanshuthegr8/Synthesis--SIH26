import india from "../data/india.json";
import type { SpatialFieldResponse } from "../types/api";

export type Ring = number[][];
export type Extent = { west: number; east: number; south: number; north: number };
export type Grid = { latitudes: number[]; longitudes: number[]; values: number[][] };
export type IndiaMask = { canvas: HTMLCanvasElement; alpha: Uint8Array; size: number; extent: Extent };
export type FieldStats = { minimum: number; maximum: number; breakpoints: number[]; clipped: boolean; scale: FieldScale };
export type FieldScale = "quantile" | "linear";

type Geometry = { type: string; coordinates: number[][][] | number[][][][] };

export const indiaRings: Ring[] = india.features.flatMap((feature: { geometry: unknown }) => {
  const geometry = feature.geometry as Geometry;
  return geometry.type === "Polygon" ? geometry.coordinates as Ring[] : (geometry.coordinates as Ring[][]).flat();
});

export function gridOf(field: SpatialFieldResponse | null): Grid | null {
  if (!field || field.status !== "AVAILABLE" || !field.values?.length || !field.latitudes?.length || !field.longitudes?.length) return null;
  return { latitudes: field.latitudes, longitudes: field.longitudes, values: field.values };
}

export function extentOf(grid: Grid): Extent {
  return {
    west: grid.longitudes[0],
    east: grid.longitudes[grid.longitudes.length - 1],
    south: grid.latitudes[0],
    north: grid.latitudes[grid.latitudes.length - 1],
  };
}

const maskSize = 2048;
const maskCache = new Map<string, IndiaMask>();

/** Rasterised India boundary over the grid extent; north is the top row of the canvas. */
export function indiaMask(extent: Extent): IndiaMask {
  const key = `${extent.west}:${extent.east}:${extent.south}:${extent.north}`;
  const cached = maskCache.get(key);
  if (cached) return cached;
  const canvas = document.createElement("canvas");
  canvas.width = maskSize;
  canvas.height = maskSize;
  const context = canvas.getContext("2d", { willReadFrequently: true })!;
  context.fillStyle = "#000";
  context.fillRect(0, 0, maskSize, maskSize);
  context.fillStyle = "#fff";
  context.beginPath();
  for (const ring of indiaRings) {
    ring.forEach(([longitude, latitude], index) => {
      const x = ((longitude - extent.west) / (extent.east - extent.west)) * maskSize;
      const y = ((extent.north - latitude) / (extent.north - extent.south)) * maskSize;
      if (index) context.lineTo(x, y);
      else context.moveTo(x, y);
    });
    context.closePath();
  }
  context.fill("evenodd");
  const pixels = context.getImageData(0, 0, maskSize, maskSize).data;
  const alpha = new Uint8Array(maskSize * maskSize);
  for (let index = 0; index < alpha.length; index += 1) alpha[index] = pixels[index * 4];
  const mask = { canvas, alpha, size: maskSize, extent };
  maskCache.set(key, mask);
  return mask;
}

export function insideIndia(mask: IndiaMask, longitude: number, latitude: number): boolean {
  const { extent, size } = mask;
  const x = Math.floor(((longitude - extent.west) / (extent.east - extent.west)) * size);
  const y = Math.floor(((extent.north - latitude) / (extent.north - extent.south)) * size);
  if (x < 0 || y < 0 || x >= size || y >= size) return false;
  return mask.alpha[y * size + x] > 127;
}

const breakpointQuantiles = [0.02, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 0.98];

/**
 * Colour scale over cells inside India. "quantile" is equal-area: each palette step covers the same share of the
 * country, so a few very cold Himalayan cells don't squeeze the plains into one colour. "linear" spaces the steps
 * evenly between the 2nd and 98th percentile, which suits mostly-zero fields such as rainfall.
 */
export function fieldStats(grid: Grid, mask: IndiaMask, scale: FieldScale = "quantile"): FieldStats {
  const inside: number[] = [];
  grid.values.forEach((row, rowIndex) => row.forEach((value, columnIndex) => {
    if (Number.isFinite(value) && insideIndia(mask, grid.longitudes[columnIndex], grid.latitudes[rowIndex])) inside.push(value);
  }));
  const sample = inside.length ? inside : grid.values.flat().filter(Number.isFinite);
  sample.sort((a, b) => a - b);
  const at = (quantile: number) => sample[Math.min(sample.length - 1, Math.max(0, Math.round(quantile * (sample.length - 1))))];
  const minimum = sample[0];
  const maximum = sample[sample.length - 1];
  const low = at(breakpointQuantiles[0]);
  const high = at(breakpointQuantiles[breakpointQuantiles.length - 1]);
  const breakpoints = scale === "quantile"
    ? breakpointQuantiles.map(at)
    : breakpointQuantiles.map((_, index) => low + ((high - low) * index) / (breakpointQuantiles.length - 1));
  if (breakpoints[breakpoints.length - 1] - breakpoints[0] < 1e-6) {
    const high = maximum === minimum ? minimum + 1 : maximum;
    breakpoints.forEach((_, index) => { breakpoints[index] = minimum + ((high - minimum) * index) / (breakpoints.length - 1); });
  }
  return { minimum, maximum, breakpoints, scale, clipped: breakpoints[0] > minimum || breakpoints[breakpoints.length - 1] < maximum };
}

export function normalise(value: number, stats: FieldStats): number {
  const { breakpoints } = stats;
  const last = breakpoints.length - 1;
  if (!Number.isFinite(value) || value <= breakpoints[0]) return 0;
  if (value >= breakpoints[last]) return 1;
  let index = 0;
  while (index < last - 1 && value > breakpoints[index + 1]) index += 1;
  const span = breakpoints[index + 1] - breakpoints[index];
  return (index + (span > 0 ? (value - breakpoints[index]) / span : 0)) / last;
}

/** Linear position between the 2nd and 98th percentile; used for height so relief stays proportional to the value. */
export function normaliseLinear(value: number, stats: FieldStats): number {
  const low = stats.breakpoints[0];
  const high = stats.breakpoints[stats.breakpoints.length - 1];
  if (!Number.isFinite(value) || high <= low) return 0;
  return Math.max(0, Math.min(1, (value - low) / (high - low)));
}

export function formatUnits(units: string | null | undefined): string {
  if (units === "C") return "°C";
  if (units === "weight") return "";
  return units ?? "";
}

/** Value with units; weights (0–1) read as percentages. */
export function formatValue(value: number | null | undefined, units: string | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (units === "weight") return `${(value * 100).toFixed(0)}%`;
  const label = formatUnits(units);
  return `${value.toFixed(digits)}${label ? ` ${label}` : ""}`;
}
