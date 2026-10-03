import { useMemo, useState, type MouseEvent } from "react";
import india from "../data/india.json";
import type { Blend, Forecast } from "../types/api";

type Layer = "blend" | "weights" | "disagreement" | "uncertainty" | string;

const bounds = { west: 65, east: 100, south: 5, north: 40 };
const width = 760;
const height = 430;

function project([longitude, latitude]: number[]): [number, number] {
  return [
    ((longitude - bounds.west) / (bounds.east - bounds.west)) * width,
    height - ((latitude - bounds.south) / (bounds.north - bounds.south)) * height,
  ];
}

function ringPath(ring: number[][]): string {
  return `${ring.map((coordinate, index) => `${index ? "L" : "M"} ${project(coordinate)[0].toFixed(1)} ${project(coordinate)[1].toFixed(1)}`).join(" ")} Z`;
}

function geometryPaths(geometry: { type: string; coordinates: number[][][] | number[][][][] }): string[] {
  if (geometry.type === "Polygon") return (geometry.coordinates as number[][][]).map(ringPath);
  return (geometry.coordinates as number[][][][]).flatMap((polygon) => polygon.map(ringPath));
}

export function ForecastMap({ forecasts, blend, variable, lead, onLocationSelect }: { forecasts: Forecast[]; blend: Blend; variable: string; lead: number; onLocationSelect?: (location: [number, number]) => void }) {
  const [layer, setLayer] = useState<Layer>("blend");
  const [selected, setSelected] = useState<[number, number]>([blend.longitude, blend.latitude]);
  const source = forecasts.find((item) => item.model_id === layer) ?? forecasts.find((item) => item.model_id === "ai");
  const featurePaths = useMemo(() => india.features.flatMap((feature: { geometry: unknown }) => geometryPaths(feature.geometry as { type: string; coordinates: number[][][] | number[][][][] })), []);
  const value = layer === "blend" ? blend.blended_value : source?.value ?? blend.blended_value;
  const projected = project(selected);
  const weights = Object.entries(blend.model_weights).sort((a, b) => b[1] - a[1]);
  const uncertaintyPosition = blend.upper_bound === blend.lower_bound
    ? 50
    : Math.max(0, Math.min(100, ((blend.blended_value - blend.lower_bound) / (blend.upper_bound - blend.lower_bound)) * 100));
  const handleMapClick = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * width;
    const y = ((event.clientY - rect.top) / rect.height) * height;
    const location: [number, number] = [
      Math.max(bounds.west, Math.min(bounds.east, bounds.west + (x / width) * (bounds.east - bounds.west))),
      Math.max(bounds.south, Math.min(bounds.north, bounds.south + ((height - y) / height) * (bounds.north - bounds.south))),
    ];
    setSelected(location);
    onLocationSelect?.(location);
  };
  return <div className="map-visual" aria-label="India forecast map">
    <div className="map-layer-controls" role="group" aria-label="Forecast map layer">
      {(["blend", "weights", ...forecasts.map((item) => item.model_id), "disagreement", "uncertainty", "regime"] as Layer[]).map((item) => <button key={item} className={layer === item ? "active" : ""} onClick={() => setLayer(item)}>{item === "blend" ? "Synthesis" : item === "weights" ? "Weights" : item}</button>)}
    </div>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" onClick={handleMapClick}>
      <rect width={width} height={height} fill="#dce9e7"/>
      <g className="map-grid-lines-svg">{Array.from({ length: 12 }, (_, index) => <line key={`v${index}`} x1={index * 70} y1="0" x2={index * 70} y2={height}/>) }{Array.from({ length: 8 }, (_, index) => <line key={`h${index}`} x1="0" y1={index * 60} x2={width} y2={index * 60}/>)}</g>
      <g className="india-boundary">{featurePaths.map((path: string, index: number) => <path key={index} d={path} />)}</g>
      <circle className="selected-location" cx={projected[0]} cy={projected[1]} r="7" />
    </svg>
    <div className="map-tooltip"><strong>{layer === "blend" ? "AIRAVAT BLEND" : layer === "weights" ? "MODEL WEIGHTS · CURRENT RUN / LEAD" : layer === "disagreement" ? "MODEL DISAGREEMENT · CURRENT RUN" : layer === "uncertainty" ? "UNCERTAINTY RANGE · CURRENT RUN" : layer === "regime" ? "REGIME SIGNAL · CURRENT RUN" : layer.toUpperCase()}</strong><span>Selected map location · {selected[1].toFixed(2)}N {selected[0].toFixed(2)}E</span><span>{layer === "disagreement" ? `${blend.disagreement.range.toFixed(1)} ${source?.unit ?? ""} range · selected point diagnostic` : layer === "uncertainty" ? `${blend.lower_bound.toFixed(1)}–${blend.upper_bound.toFixed(1)} ${source?.unit ?? ""} · run-level range` : layer === "weights" ? "Run-level weights; not a geographic field" : layer === "regime" ? `${blend.regime.replace(/_/g, " ")} · ${Math.round(blend.regime_confidence * 100)}% rule-based confidence` : `Current backend forecast: ${value.toFixed(1)} ${source?.unit ?? ""} · run-level value`}</span><small>{layer === "regime" ? "Run-level classification; not a geographic regime field" : `${blend.regime.replace(/_/g, " ")} · ${blend.disagreement.level}`}</small></div>
    {layer === "uncertainty" && <div className="uncertainty-diagnostic"><div><strong>Run-level uncertainty</strong><span>{blend.lower_bound.toFixed(1)}–{blend.upper_bound.toFixed(1)} {source?.unit ?? ""}</span></div><div className="uncertainty-bar" aria-label={`Run-level uncertainty from ${blend.lower_bound.toFixed(1)} to ${blend.upper_bound.toFixed(1)} ${source?.unit ?? ""}`}><i /><b style={{ left: `${uncertaintyPosition}%` }} /></div><small>Blended value {blend.blended_value.toFixed(1)} {source?.unit ?? ""} · not a calibrated confidence interval · not spatial</small></div>}
    {layer === "regime" && <div className="regime-diagnostic"><strong>{blend.regime.replace(/_/g, " ")}</strong><span>{Math.round(blend.regime_confidence * 100)}% rule-based confidence</span><small>Current run classification · not a geographic regime field</small></div>}
    {layer === "weights" && <div className="map-weight-legend"><strong>Current run / {lead}h</strong>{weights.map(([model, weight]) => <span key={model}>{model.toUpperCase()} {Math.round(weight * 100)}%</span>)}</div>}
    <div className="map-data-note">India boundary and coordinate context are geographic. Forecast values and diagnostics are run-level; no spatial forecast grid is provided.</div>
    <div className="map-attribution">India boundary: DataMeet / Natural Earth-derived GeoJSON · synthetic forecast values remain labeled DEMO MODE</div>
  </div>;
}
