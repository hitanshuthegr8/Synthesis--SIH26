import { useState } from "react";
import { CheckCircle2, FlaskConical } from "lucide-react";
import { synthesis } from "../api";
import { MethodBars, NumberLine, type MethodBar } from "../components/charts";
import { Card, KeyValue, Loading, Notice, Segmented } from "../components/ui";
import { number, percent, signed, unitLabel } from "../lib/format";
import { useAsync } from "../lib/useAsync";

// The point engine's four demo members (GFS/IFS deterministic, GEFS ensemble, an AI model); colours reuse the
// validated categorical order with the ensemble in the fourth slot.
const MODELS: Record<string, { label: string; kind: string; color: string }> = {
  gfs: { label: "GFS", kind: "Physics NWP", color: "var(--series-gfs)" },
  ecmwf: { label: "IFS", kind: "Physics NWP", color: "var(--series-ifs)" },
  ai: { label: "AI model", kind: "AI / ML", color: "var(--series-aifs)" },
  gefs: { label: "GEFS", kind: "Ensemble mean", color: "var(--series-4)" },
};

const SCENARIOS = [
  { id: "normal", label: "Normal day", variable: "temperature", blurb: "Models agree; skill weights dominate." },
  { id: "heavy_rain", label: "Heavy rain", variable: "precipitation", blurb: "Monsoon burst; the regime engine flags HEAVY_RAIN from the high-end member." },
  { id: "model_conflict", label: "Model conflict", variable: "precipitation", blurb: "GFS and GEFS far wetter than IFS and AI; disagreement widens the uncertainty band." },
  { id: "", label: "Random (wind)", variable: "wind_speed", blurb: "Seeded mock members for 10 m wind." },
];

export function Lab() {
  const [scenario, setScenario] = useState("model_conflict");
  const [lead, setLead] = useState(24);
  const chosen = SCENARIOS.find((item) => item.id === scenario)!;
  const run = useAsync(() => synthesis.pipeline(chosen.variable, lead, chosen.id || undefined), [scenario, lead]);
  const data = run.data;
  const units = unitLabel(data?.forecasts[0]?.unit ?? "");

  return <div className="page lab">
    <Notice tone="info" title="Offline demonstration point (Mumbai, 19.08°N 72.88°E)">These scenarios use clearly-labelled synthetic member values so the regime-, disagreement- and skill-aware logic can be shown on demand. Live gridded blending is on the Blend Explorer.</Notice>
    <div className="page-toolbar">
      <Segmented label="Scenario" value={scenario} onChange={setScenario} options={SCENARIOS.map((item) => ({ value: item.id, label: item.label }))} />
      <Segmented label="Lead" value={lead} onChange={setLead} options={[24, 48, 72].map((value) => ({ value, label: `+${value} h` }))} />
      <span className="toolbar-note">{chosen.blurb}</span>
    </div>
    {run.status === "loading" && !data && <Card><Loading label="Running the pipeline…" /></Card>}
    {run.status === "error" && <Notice tone="error" title="Pipeline failed">{run.error}</Notice>}
    {data && <>
      <Card eyebrow="MEMBERS → BLEND" title={<>{number(data.blend.blended_value)} <small>{units}</small> <span className="title-note">range {number(data.blend.lower_bound)}–{number(data.blend.upper_bound)} {units}</span></>}>
        <NumberLine
          models={data.forecasts.map((forecast) => ({ id: forecast.model_id, label: MODELS[forecast.model_id]?.label ?? forecast.model_id, value: forecast.value, color: MODELS[forecast.model_id]?.color ?? "var(--text-2)" }))}
          blend={data.blend.blended_value}
          lower={data.blend.lower_bound}
          upper={data.blend.upper_bound}
          observation={data.verification.observation_value}
          units={units}
        />
      </Card>
      <div className="three-col">
        <Card eyebrow="WEATHER REGIME" title={data.blend.regime.replace("_", " ")}>
          <KeyValue items={[
            ["Rule confidence", percent(data.blend.regime_confidence)],
            ["Disagreement", <span className={`pill level-${data.blend.disagreement.level.toLowerCase()}`}>{data.blend.disagreement.level}</span>],
            ["Member spread", `${number(data.blend.disagreement.range)} ${units} (σ ${number(data.blend.disagreement.std)})`],
            ["Fallback mode", data.blend.fallback_mode ? "yes" : "no"],
          ]} />
        </Card>
        <Card eyebrow="SKILL WEIGHTS" title="Who is trusted">
          <MethodBars units="%" better="higher" digits={0} bars={Object.entries(data.blend.model_weights).sort((a, b) => b[1] - a[1]).map(([model, weight]) => ({ key: model, label: MODELS[model]?.label ?? model, value: weight * 100, kind: "baseline" as const }))} caption="Weight (%) from inverse historical MAE for this variable and lead." />
        </Card>
        <Card eyebrow="AUTOPSY" title="Error vs demo observation">
          <MethodBars units={units} bars={[
            ...Object.entries(data.verification.model_errors).map(([model, error]): MethodBar => ({ key: model, label: MODELS[model]?.label ?? model, value: Math.abs(error), kind: "baseline", note: `signed ${signed(error)}` })),
            { key: "blend", label: "AIRAVAT", value: data.verification.absolute_error, kind: "synthesis" },
          ]} caption="Absolute error against the scenario's synthetic observation." />
        </Card>
      </div>
      <div className="two-col">
        <Card eyebrow="EXPLANATION" title="Why this blend">
          <ul className="explain-list">{data.blend.explanation.map((line) => <li key={line}><FlaskConical size={14} />{line}</li>)}</ul>
        </Card>
        <Card eyebrow="PIPELINE TRACE" title={<code>{data.run_id.slice(0, 18)}…</code>}>
          <ol className="trace">{data.trace.stages.map((stage) => <li key={stage.name}><CheckCircle2 size={14} /><span>{stage.name.replace(/_/g, " ")}</span><em>{stage.regime ?? stage.level ?? (stage.record_count !== undefined ? `${stage.record_count} records` : stage.status)}</em></li>)}</ol>
          <p className="fine">config {data.blend.config_hash} · algorithm v{data.blend.algorithm_version} · dataset {data.blend.dataset_version}</p>
        </Card>
      </div>
    </>}
  </div>;
}
