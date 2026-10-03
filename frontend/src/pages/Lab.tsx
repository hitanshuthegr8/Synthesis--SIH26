import { useState } from "react";
import { CheckCircle2, CircleOff, FlaskConical } from "lucide-react";
import { synthesis } from "../api";
import { MethodBars, NumberLine, type MethodBar } from "../components/charts";
import { Card, KeyValue, Loading, Notice, Segmented } from "../components/ui";
import { number, percent, signed, unitLabel } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import type { PipelineScenario, PipelineSource } from "../types/synthesis";

// The pipeline's four benchmark members (GFS/IFS deterministic, GEFS ensemble, an AI model); colours reuse the
// validated categorical order with the ensemble in the fourth slot.
const MODELS: Record<PipelineSource, { label: string; kind: string; color: string }> = {
  gfs: { label: "GFS", kind: "Physics NWP", color: "var(--series-gfs)" },
  ecmwf: { label: "IFS", kind: "Physics NWP", color: "var(--series-ifs)" },
  ai: { label: "AI model", kind: "AI / ML", color: "var(--series-aifs)" },
  gefs: { label: "GEFS", kind: "Ensemble mean", color: "var(--series-4)" },
};
const label = (model: string) => MODELS[model as PipelineSource]?.label ?? model;

const SCENARIOS: { id: PipelineScenario; label: string; blurb: string }[] = [
  { id: "normal", label: "Normal day", blurb: "Models agree; skill weights dominate." },
  { id: "heavy_rain", label: "Heavy rain", blurb: "Monsoon burst; the regime engine flags HEAVY_RAIN from the high-end member." },
  { id: "model_conflict", label: "Model conflict", blurb: "Members split into wet and dry camps; disagreement widens the uncertainty band." },
  { id: "model_disagreement", label: "Disagreement", blurb: "Broad member spread without a clear outlier." },
  { id: "model_failure", label: "Model failure", blurb: "One member returns an implausible value; weighting down-ranks it." },
];

export function Lab() {
  const [scenario, setScenario] = useState<PipelineScenario>("model_conflict");
  const [lead, setLead] = useState(24);
  const [offline, setOffline] = useState<PipelineSource[]>([]);
  const chosen = SCENARIOS.find((item) => item.id === scenario)!;
  const run = useAsync(() => synthesis.pipeline(scenario, lead, offline), [scenario, lead, offline.join(",")]);
  const data = run.data;
  const units = unitLabel(data?.forecasts[0]?.unit ?? "");
  const toggle = (source: PipelineSource) => setOffline((current) => current.includes(source) ? current.filter((item) => item !== source) : [...current, source]);

  return <div className="page lab">
    <Notice tone="info" title="Offline demonstration point (Mumbai, 19.08°N 72.88°E)">These scenarios use clearly labelled synthetic member values so the regime-, disagreement- and skill-aware pipeline can be shown on demand, including source outages. Live gridded blending is on the Blend explorer.</Notice>
    <div className="page-toolbar">
      <Segmented label="Scenario" value={scenario} onChange={setScenario} options={SCENARIOS.map((item) => ({ value: item.id, label: item.label }))} />
      <Segmented label="Lead" value={lead} onChange={setLead} options={[24, 48, 72].map((value) => ({ value, label: `+${value} h` }))} />
      <span className="toolbar-note">{chosen.blurb}</span>
    </div>
    <div className="page-toolbar">
      <span className="field-label"><CircleOff size={12} /> Take a source offline</span>
      <div className="chip-set">{(Object.keys(MODELS) as PipelineSource[]).map((source) => <button key={source} className={`chip ${offline.includes(source) ? "on" : ""}`} onClick={() => toggle(source)}>{MODELS[source].label}</button>)}</div>
    </div>
    {run.status === "loading" && !data && <Card><Loading label="Running the forecast cycle…" /></Card>}
    {run.status === "error" && <Notice tone="error" title="Pipeline could not blend">{run.error}</Notice>}
    {data && run.status !== "error" && <>
      {data.status === "stale" && <Notice tone="warn" title="No usable source: showing the last good run">Every selected source is offline, so the pipeline serves the most recent successful blend{data.trace.stale_from_run_id ? ` (${data.trace.stale_from_run_id})` : ""}, marked stale, instead of inventing a forecast.</Notice>}
      <Card eyebrow="MEMBERS → BLEND" title={<>{number(data.blend.blended_value)} <small>{units}</small> <span className="title-note">range {number(data.blend.lower_bound)}–{number(data.blend.upper_bound)} {units}</span></>}>
        <NumberLine
          models={data.forecasts.map((forecast) => ({ id: forecast.model_id, label: label(forecast.model_id), value: forecast.value, color: MODELS[forecast.model_id as PipelineSource]?.color ?? "var(--text-2)" }))}
          blend={data.blend.blended_value}
          lower={data.blend.lower_bound}
          upper={data.blend.upper_bound}
          observation={data.verification.observation_value}
          units={units}
        />
      </Card>
      <div className="three-col">
        <Card eyebrow="WEATHER REGIME" title={data.blend.regime.replace(/_/g, " ")}>
          <KeyValue items={[
            ["Rule confidence", percent(data.blend.regime_confidence)],
            ["Disagreement", <span className={`pill level-${data.blend.disagreement.level.toLowerCase()}`}>{data.blend.disagreement.level}</span>],
            ["Member spread", `${number(data.blend.disagreement.range)} ${units} (σ ${number(data.blend.disagreement.std)})`],
            ["Sources used", `${data.forecasts.length} of 4${offline.length ? ` · offline: ${offline.map(label).join(", ")}` : ""}`],
            ["Fallback mode", data.blend.fallback_mode ? "yes" : "no"],
          ]} />
        </Card>
        <Card eyebrow="SKILL WEIGHTS" title="Who is trusted">
          <MethodBars units="%" better="higher" digits={0} bars={Object.entries(data.blend.model_weights).sort((a, b) => b[1] - a[1]).map(([model, weight]) => ({ key: model, label: label(model), value: weight * 100, kind: "baseline" as const }))} caption="Weight (%) from historical skill, adjusted for regime and member plausibility." />
        </Card>
        <Card eyebrow="AUTOPSY" title="Error vs demo observation">
          <MethodBars units={units} bars={[
            ...Object.entries(data.verification.model_errors).map(([model, error]): MethodBar => ({ key: model, label: label(model), value: Math.abs(error), kind: "baseline", note: `signed ${signed(error)}` })),
            { key: "blend", label: "AIRAVAT", value: data.verification.absolute_error, kind: "synthesis" },
          ]} caption={data.autopsy.assessment} />
        </Card>
      </div>
      <div className="two-col">
        <Card eyebrow="EXPLANATION" title="Why this blend">
          <ul className="explain-list">{data.blend.explanation.map((line) => <li key={line}><FlaskConical size={14} />{line}</li>)}</ul>
        </Card>
        <Card eyebrow="PIPELINE TRACE" title={<code>{data.run_id}</code>}>
          <ol className="trace">{data.trace.steps.map((step) => <li key={step.name}><CheckCircle2 size={14} /><span>{step.name.replace(/_/g, " ")}</span><em>{step.details[0] ?? step.status}</em></li>)}</ol>
          <p className="fine">{data.blend.algorithm} · {data.trace.algorithm_version} · dataset {data.trace.dataset_version} · config {data.trace.configuration_hash.slice(0, 12)} · {data.trace.duration_ms} ms</p>
        </Card>
      </div>
    </>}
  </div>;
}
