import { useId, useMemo, type MouseEvent } from "react";
import india from "../data/india.json";
import type { SpatialFieldResponse } from "../types/api";

const width = 820;
const height = 470;
const bounds = { west: 65, east: 100, south: 5, north: 40 };
const padding = 22;
const centerLatitude = (bounds.south + bounds.north) / 2;
const longitudeCorrection = Math.cos((centerLatitude * Math.PI) / 180);
const scale = Math.min(
  (width - padding * 2) / ((bounds.east - bounds.west) * longitudeCorrection),
  (height - padding * 2) / (bounds.north - bounds.south),
);
const projectedWidth = (bounds.east - bounds.west) * longitudeCorrection * scale;
const projectedHeight = (bounds.north - bounds.south) * scale;
const originX = (width - projectedWidth) / 2;
const originY = (height - projectedHeight) / 2;

function project(longitude: number, latitude: number): [number, number] {
  return [
    originX + (longitude - bounds.west) * longitudeCorrection * scale,
    originY + (bounds.north - latitude) * scale,
  ];
}

function unproject(x: number, y: number): [number, number] {
  return [
    bounds.west + (x - originX) / (longitudeCorrection * scale),
    bounds.north - (y - originY) / scale,
  ];
}

function ringPath(ring: number[][]): string {
  return `${ring.map((coordinate, index) => `${index ? "L" : "M"} ${project(coordinate[0], coordinate[1])[0].toFixed(1)} ${project(coordinate[0], coordinate[1])[1].toFixed(1)}`).join(" ")} Z`;
}

function paths(geometry: { type: string; coordinates: number[][][] | number[][][][] }): string[] {
  return geometry.type === "Polygon"
    ? (geometry.coordinates as number[][][]).map(ringPath)
    : (geometry.coordinates as number[][][][]).flatMap((polygon) => polygon.map(ringPath));
}

function geometryPath(geometry: { type: string; coordinates: number[][][] | number[][][][] }): string {
  return paths(geometry).join(" ");
}

function color(value: number, minimum: number, maximum: number): string {
  const ratio = maximum === minimum ? 0.5 : Math.max(0, Math.min(1, (value - minimum) / (maximum - minimum)));
  const hue = 214 - ratio * 184;
  return `hsl(${hue} 62% ${42 + (1 - ratio) * 13}%)`;
}

export function SpatialFieldMap({ field, title, onCellSelect }: {
  field: SpatialFieldResponse | null;
  title: string;
  onCellSelect?: (value: number, latitude: number, longitude: number) => void;
}) {
  const featurePaths = useMemo(() => india.features.flatMap((feature: { geometry: unknown }) => paths(feature.geometry as { type: string; coordinates: number[][][] | number[][][][] })), []);
  const boundaryPath = useMemo(() => india.features.map((feature: { geometry: unknown }) => geometryPath(feature.geometry as { type: string; coordinates: number[][][] | number[][][][] })).join(" "), []);
  const clipId = `india-field-clip-${useId().replace(/:/g, "")}`;
  if (!field || field.status !== "AVAILABLE" || !field.values || !field.latitudes || !field.longitudes) {
    return <div className="field-empty"><span>GRID FIELD</span><strong>{title}</strong><p>No spatial field is available for this request.</p></div>;
  }
  const gridValues = field.values;
  const values = gridValues.flat();
  const latitudes = field.latitudes;
  const longitudes = field.longitudes;
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const rowStep = Math.max(1, Math.floor(field.values.length / 24));
  const colStep = Math.max(1, Math.floor(field.values[0].length / 28));
  const handleClick = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const [longitude, latitude] = unproject(
      ((event.clientX - rect.left) / rect.width) * width,
      ((event.clientY - rect.top) / rect.height) * height,
    );
    const row = Math.max(0, Math.min(latitudes.length - 1, Math.round((latitude - bounds.south) / 0.25)));
    const column = Math.max(0, Math.min(longitudes.length - 1, Math.round((longitude - bounds.west) / 0.25)));
    onCellSelect?.(gridValues[row][column], latitudes[row], longitudes[column]);
  };
  return <div className="field-map-wrap">
    <div className="field-map-header"><div><span className="eyebrow">SPATIAL FIELD · 141 × 141</span><strong>{title}</strong></div><span>{minimum.toFixed(1)}–{maximum.toFixed(1)} {field.units}</span></div>
    <svg className="field-map" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title} onClick={handleClick}>
      <rect width={width} height={height} fill="#e6efed" />
      <defs><clipPath id={clipId}><path d={boundaryPath} clipRule="evenodd" /></clipPath></defs>
      <g clipPath={`url(#${clipId})`}>
      {gridValues.filter((_, row) => row % rowStep === 0).flatMap((row, rowIndex) => row.filter((_, column) => column % colStep === 0).map((value, columnIndex) => {
        const sourceRow = rowIndex * rowStep;
        const sourceColumn = columnIndex * colStep;
        const [x, y] = project(longitudes[sourceColumn], latitudes[sourceRow]);
        const [nextX] = project(longitudes[Math.min(sourceColumn + colStep, longitudes.length - 1)], latitudes[sourceRow]);
        const [, nextY] = project(longitudes[sourceColumn], latitudes[Math.min(sourceRow + rowStep, latitudes.length - 1)]);
        const cellWidth = nextX - x || longitudeCorrection * scale * 0.25;
        const cellHeight = y - nextY || scale * 0.25;
        return <rect key={`${sourceRow}-${sourceColumn}`} x={x - cellWidth / 2} y={y - cellHeight / 2} width={cellWidth} height={cellHeight} fill={color(value, minimum, maximum)} opacity=".82" />;
      }))}
      </g>
      <g className="india-boundary">{featurePaths.map((path, index) => <path key={index} d={path} />)}</g>
    </svg>
    <div className="field-legend"><span>cooler</span><i /><span>warmer</span><small>Click a cell to inspect its value</small></div>
  </div>;
}
