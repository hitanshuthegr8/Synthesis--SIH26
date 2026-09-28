import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import type { SpatialFieldResponse } from "../types/api";
import { FieldTerrain3D } from "./FieldTerrain3D";
import { extentOf, fieldStats, formatValue, gridOf, indiaMask, indiaRings, normalise, type FieldScale, type FieldStats, type Grid } from "./fieldGeometry";
import { paletteGradient, paletteRgb, type FieldPalette } from "./fieldPalette";

type ViewMode = "3d" | "2d";

export function SpatialFieldMap({ field, title, palette = "thermal", scale = "quantile", mode: forcedMode, compact = false, onCellSelect }: {
  field: SpatialFieldResponse | null;
  title: string;
  palette?: FieldPalette;
  scale?: FieldScale;
  mode?: ViewMode;
  compact?: boolean;
  onCellSelect?: (value: number, latitude: number, longitude: number) => void;
}) {
  const [chosenMode, setChosenMode] = useState<ViewMode>("3d");
  const [webglUnsupported, setWebglUnsupported] = useState(false);
  const grid = useMemo(() => gridOf(field), [field]);
  const mask = useMemo(() => grid && indiaMask(extentOf(grid)), [grid]);
  const stats = useMemo(() => grid && mask && fieldStats(grid, mask, scale), [grid, mask, scale]);
  if (!grid || !mask || !stats) {
    return <div className="field-empty"><span className="eyebrow">GRID FIELD</span><strong>{title}</strong><p>{field?.reason ?? "No spatial field is available for this request."}</p></div>;
  }
  const units = field?.units ?? "";
  const mode = forcedMode ?? chosenMode;
  const show3d = mode === "3d" && !webglUnsupported;
  const ticks = stats.breakpoints.filter((_, index) => index % 2 === 0);
  return <div className={`field-map-wrap${compact ? " compact" : ""}`}>
    <div className="field-map-header">
      <div><span className="eyebrow">{grid.latitudes.length} × {grid.longitudes.length} · 0.25°</span><strong>{title}</strong></div>
      <div className="field-map-header-side">
        {!compact && <span className="range">{formatValue(stats.minimum, units)} to {formatValue(stats.maximum, units)} over India</span>}
        {!forcedMode && !webglUnsupported && <div className="segmented small" role="group" aria-label="Map view">
          <button className={chosenMode === "3d" ? "active" : ""} onClick={() => setChosenMode("3d")}>3D</button>
          <button className={chosenMode === "2d" ? "active" : ""} onClick={() => setChosenMode("2d")}>2D</button>
        </div>}
      </div>
    </div>
    {show3d
      ? <FieldTerrain3D grid={grid} stats={stats} mask={mask} palette={palette} units={units} onCellSelect={onCellSelect} onUnsupported={() => setWebglUnsupported(true)} />
      : <FlatFieldMap grid={grid} stats={stats} palette={palette} title={title} units={units} compact={compact} onCellSelect={onCellSelect} />}
    <div className="field-legend">
      <div className="legend-scale">
        <span className="legend-bar" style={{ background: paletteGradient(palette) }} />
        <div className="legend-ticks">{ticks.map((value, index) => <span key={index}>{stats.clipped && index === 0 ? "≤ " : ""}{stats.clipped && index === ticks.length - 1 ? "≥ " : ""}{formatValue(value, units, units === "weight" ? 0 : 1)}</span>)}</div>
      </div>
      {!compact && <small>{show3d ? "Height is linear in value · " : ""}{stats.scale === "quantile" ? "equal-area colour scale (each step covers the same share of India)" : "linear colour scale, 2nd–98th percentile"}</small>}
    </div>
  </div>;
}

const width = 820;
const height = 560;
const bounds = { west: 65, east: 100, south: 5, north: 40 };
const padding = 16;
const longitudeCorrection = Math.cos((((bounds.south + bounds.north) / 2) * Math.PI) / 180);
const scaleFactor = Math.min(
  (width - padding * 2) / ((bounds.east - bounds.west) * longitudeCorrection),
  (height - padding * 2) / (bounds.north - bounds.south),
);
const originX = (width - (bounds.east - bounds.west) * longitudeCorrection * scaleFactor) / 2;
const originY = (height - (bounds.north - bounds.south) * scaleFactor) / 2;

function project(longitude: number, latitude: number): [number, number] {
  return [originX + (longitude - bounds.west) * longitudeCorrection * scaleFactor, originY + (bounds.north - latitude) * scaleFactor];
}

function unproject(x: number, y: number): [number, number] {
  return [bounds.west + (x - originX) / (longitudeCorrection * scaleFactor), bounds.north - (y - originY) / scaleFactor];
}

const indiaPath = indiaRings.map((ring) => `${ring.map(([longitude, latitude], index) => {
  const [x, y] = project(longitude, latitude);
  return `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
}).join(" ")}Z`).join(" ");

/** Flat map: the field is painted into a 141×141 image, scaled to the projection and clipped to India. */
function FlatFieldMap({ grid, stats, palette, title, units, compact, onCellSelect }: {
  grid: Grid;
  stats: FieldStats;
  palette: FieldPalette;
  title: string;
  units: string;
  compact: boolean;
  onCellSelect?: (value: number, latitude: number, longitude: number) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<{ x: number; y: number; value: number; latitude: number; longitude: number } | null>(null);
  const { values, latitudes, longitudes } = grid;
  const latitudeStep = latitudes[1] - latitudes[0];
  const longitudeStep = longitudes[1] - longitudes[0];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const image = document.createElement("canvas");
    image.width = longitudes.length;
    image.height = latitudes.length;
    const imageContext = image.getContext("2d")!;
    const pixels = imageContext.createImageData(image.width, image.height);
    values.forEach((row, rowIndex) => row.forEach((value, columnIndex) => {
      const [r, g, b] = paletteRgb(palette, normalise(value, stats));
      const offset = ((latitudes.length - 1 - rowIndex) * longitudes.length + columnIndex) * 4;
      pixels.data.set([r * 255, g * 255, b * 255, 255], offset);
    }));
    imageContext.putImageData(pixels, 0, 0);
    context.clearRect(0, 0, width, height);
    const [left, top] = project(longitudes[0] - longitudeStep / 2, latitudes[latitudes.length - 1] + latitudeStep / 2);
    const [right, bottom] = project(longitudes[longitudes.length - 1] + longitudeStep / 2, latitudes[0] - latitudeStep / 2);
    const boundary = new Path2D(indiaPath);
    context.save();
    context.clip(boundary, "evenodd");
    context.imageSmoothingEnabled = false;
    context.drawImage(image, left, top, right - left, bottom - top);
    context.restore();
    context.lineWidth = 1.1;
    context.strokeStyle = "rgba(210, 240, 234, 0.75)";
    context.stroke(boundary);
  }, [values, latitudes, longitudes, latitudeStep, longitudeStep, palette, stats]);

  const cellAt = (event: MouseEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const [longitude, latitude] = unproject(((event.clientX - rect.left) / rect.width) * width, ((event.clientY - rect.top) / rect.height) * height);
    const row = Math.round((latitude - latitudes[0]) / latitudeStep);
    const column = Math.round((longitude - longitudes[0]) / longitudeStep);
    if (row < 0 || column < 0 || row >= latitudes.length || column >= longitudes.length) return null;
    return { x: event.clientX - rect.left, y: event.clientY - rect.top, value: values[row][column], latitude: latitudes[row], longitude: longitudes[column] };
  };

  return <div className={`flat-map${compact ? " compact" : ""}`}>
    <canvas
      ref={canvasRef}
      className="field-map"
      role="img"
      aria-label={title}
      onMouseMove={(event) => setHover(cellAt(event))}
      onMouseLeave={() => setHover(null)}
      onClick={(event) => {
        const cell = cellAt(event);
        if (cell) onCellSelect?.(cell.value, cell.latitude, cell.longitude);
      }}
    />
    {hover && <div className="terrain-tooltip" style={{ left: hover.x, top: hover.y }}>
      <strong>{formatValue(hover.value, units)}</strong>
      <span>{hover.latitude.toFixed(2)}°N · {hover.longitude.toFixed(2)}°E</span>
    </div>}
  </div>;
}
