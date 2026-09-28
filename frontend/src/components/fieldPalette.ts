export type FieldPalette = "thermal" | "error" | "rain" | "wind" | "spread" | "weight_GFS" | "weight_ECMWF" | "weight_AIFS";

// Sequential ramps run dark → light so low values recede into the dark map surface.
const stops: Record<FieldPalette, string[]> = {
  thermal: ["#313695", "#4575b4", "#74add1", "#abd9e9", "#e0f3f8", "#fee090", "#fdae61", "#f46d43", "#d73027", "#a50026"],
  error: ["#1d2b53", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"],
  rain: ["#12283a", "#184f95", "#2a78d6", "#5598e7", "#9ec5f4", "#eef5fd"],
  wind: ["#1c1936", "#3b2f8a", "#6a5bd6", "#9085e9", "#c9c2f5", "#f3f1fe"],
  spread: ["#26170f", "#6e2f11", "#b94a1d", "#ec835a", "#f6bc9e", "#fdf0e8"],
  weight_GFS: ["#0f2135", "#1c5cab", "#3987e5", "#86b6ef", "#e1edfc"],
  weight_ECMWF: ["#27180f", "#8f3a16", "#d95926", "#f09a73", "#fbe3d7"],
  weight_AIFS: ["#0a2820", "#0f6b4c", "#199e70", "#6cd3a9", "#d9f6ea"],
};

const parsed = Object.fromEntries(
  Object.entries(stops).map(([name, colors]) => [name, colors.map(hexToRgb)]),
) as Record<FieldPalette, [number, number, number][]>;

function hexToRgb(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16 & 255) / 255, (value >> 8 & 255) / 255, (value & 255) / 255];
}

/** sRGB colour (0–1 channels) at position t ∈ [0, 1] along the palette. */
export function paletteRgb(palette: FieldPalette, t: number): [number, number, number] {
  const colors = parsed[palette];
  const position = Math.max(0, Math.min(1, t)) * (colors.length - 1);
  const index = Math.min(colors.length - 2, Math.floor(position));
  const ratio = position - index;
  const [from, to] = [colors[index], colors[index + 1]];
  return [from[0] + (to[0] - from[0]) * ratio, from[1] + (to[1] - from[1]) * ratio, from[2] + (to[2] - from[2]) * ratio];
}

export function paletteCss(palette: FieldPalette, t: number): string {
  const [r, g, b] = paletteRgb(palette, t);
  return `rgb(${Math.round(r * 255)} ${Math.round(g * 255)} ${Math.round(b * 255)})`;
}

export function paletteGradient(palette: FieldPalette): string {
  return `linear-gradient(90deg, ${stops[palette].join(", ")})`;
}
