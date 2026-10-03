import { SOURCE_META, SOURCE_ORDER, number } from "../lib/format";
import type { SourceId } from "../types/synthesis";

/** Stacked share bar: one segment per source in fixed categorical order, 2 px gaps between segments. */
export function WeightBar({ weights, label }: { weights: Partial<Record<SourceId, number>>; label?: string }) {
  const sources = SOURCE_ORDER.filter((source) => weights[source] !== undefined);
  const total = sources.reduce((sum, source) => sum + (weights[source] ?? 0), 0) || 1;
  return <div className="weight-bar" role="img" aria-label={`${label ?? "Weights"}: ${sources.map((source) => `${SOURCE_META[source].short} ${Math.round(((weights[source] ?? 0) / total) * 100)}%`).join(", ")}`}>
    {sources.map((source) => {
      const share = (weights[source] ?? 0) / total;
      return <span key={source} className="segment" style={{ flexGrow: share, background: SOURCE_META[source].color }} data-tip={`${SOURCE_META[source].label}: ${(share * 100).toFixed(1)}%`}>
        {share >= 0.16 && <b>{Math.round(share * 100)}%</b>}
      </span>;
    })}
  </div>;
}

export function SourceLegend({ sources }: { sources: SourceId[] }) {
  return <div className="legend-row">{SOURCE_ORDER.filter((source) => sources.includes(source)).map((source) => <span key={source}><i style={{ background: SOURCE_META[source].color }} />{SOURCE_META[source].label}<em>{SOURCE_META[source].kind}</em></span>)}</div>;
}

export type MethodBar = { key: string; label: string; value: number; kind: "source" | "baseline" | "synthesis"; source?: SourceId; note?: string };

/** Horizontal bars for one measure; single series, so identity is carried by the row label. */
export function MethodBars({ bars, units, caption, better = "lower", digits = 2 }: { bars: MethodBar[]; units: string; caption?: string; better?: "lower" | "higher"; digits?: number }) {
  const maximum = Math.max(...bars.map((bar) => bar.value), 1e-9);
  const best = better === "lower" ? Math.min(...bars.map((bar) => bar.value)) : Math.max(...bars.map((bar) => bar.value));
  return <figure className="method-bars">
    {bars.map((bar) => <div key={bar.key} className={`method-row ${bar.kind}${bar.value === best ? " best" : ""}`} data-tip={`${bar.label}: ${number(bar.value, 3)} ${units}${bar.note ? ` · ${bar.note}` : ""}`}>
      <span className="method-label">{bar.source && <i style={{ background: SOURCE_META[bar.source].color }} />}{bar.label}</span>
      <span className="method-track"><span className="method-fill" style={{ width: `${(bar.value / maximum) * 100}%`, background: bar.source ? SOURCE_META[bar.source].color : undefined }} /></span>
      <span className="method-value">{number(bar.value, digits)}<small>{units}</small></span>
    </div>)}
    {caption && <figcaption>{caption}</figcaption>}
  </figure>;
}

/** Point forecasts on one axis: model dots, the blend with its uncertainty band, and the verifying observation. */
export function NumberLine({ models, blend, lower, upper, observation, units }: {
  models: { id: string; label: string; value: number; color: string }[];
  blend: number;
  lower: number;
  upper: number;
  observation?: number;
  units: string;
}) {
  const values = [...models.map((model) => model.value), blend, lower, upper, ...(observation !== undefined ? [observation] : [])];
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const pad = (maximum - minimum) * 0.08 || 1;
  const low = minimum - pad;
  const high = maximum + pad;
  const x = (value: number) => `${((value - low) / (high - low)) * 100}%`;
  const ticks = Array.from({ length: 5 }, (_, index) => low + ((high - low) * index) / 4);
  return <div className="number-line" role="img" aria-label={`Model forecasts ${models.map((model) => `${model.label} ${model.value.toFixed(1)}`).join(", ")}; blend ${blend.toFixed(1)} ${units}`}>
    <div className="nl-track">
      <span className="nl-band" style={{ left: x(lower), width: `calc(${x(upper)} - ${x(lower)})` }} data-tip={`Uncertainty range ${lower.toFixed(1)}–${upper.toFixed(1)} ${units}`} />
      {models.map((model, index) => <span key={model.id} className="nl-dot" style={{ left: x(model.value), background: model.color, top: `${14 + (index % 2) * 18}px` }} data-tip={`${model.label}: ${model.value.toFixed(1)} ${units}`}><b>{model.label}</b></span>)}
      <span className="nl-blend" style={{ left: x(blend) }} data-tip={`AIRAVAT blend: ${blend.toFixed(1)} ${units}`}><b>Blend {blend.toFixed(1)}</b></span>
      {observation !== undefined && <span className="nl-obs" style={{ left: x(observation) }} data-tip={`Demo observation: ${observation.toFixed(1)} ${units}`}><b>Obs {observation.toFixed(1)}</b></span>}
    </div>
    <div className="nl-axis">{ticks.map((tick) => <span key={tick} style={{ left: x(tick) }}>{Math.round(tick) || 0}</span>)}</div>
  </div>;
}

export function Progress({ value, total }: { value: number; total: number }) {
  const share = total ? Math.min(1, value / total) : 0;
  return <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={value}><span style={{ width: `${share * 100}%` }} /></div>;
}
