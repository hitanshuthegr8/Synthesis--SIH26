import { useState } from "react";
import { synthesis } from "../api";
import { useApp } from "../app/context";
import { MethodBars, SourceLegend, WeightBar, type MethodBar } from "../components/charts";
import { SpatialFieldMap } from "../components/SpatialFieldMap";
import { Card, Loading, Notice, Segmented, SourceTag, Stat } from "../components/ui";
import { SOURCE_META, SOURCE_ORDER, cycleLabel, number, plural, signed, unitLabel } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import type { SkillSummary, SourceId, VariableId } from "../types/synthesis";

const SKILL_VARIABLES: { value: VariableId; label: string }[] = [
  { value: "temperature", label: "2 m temperature" },
  { value: "wind_speed", label: "10 m wind" },
];
const SKILL_LEADS = [24, 48, 72];
const REFERENCES: { key: "mean" | "GFS" | "ECMWF"; label: string }[] = [
  { key: "mean", label: "Mean of GFS + IFS analyses (used for weights)" },
  { key: "GFS", label: "GFS analysis only" },
  { key: "ECMWF", label: "IFS analysis only" },
];

export function Reliability() {
  const { cycle } = useApp();
  const [variable, setVariable] = useState<VariableId>("temperature");
  const [lead, setLead] = useState(24);
  const skill = useAsync(() => synthesis.skill(variable, lead, cycle), [variable, lead, cycle]);
  const byLead = useAsync(() => Promise.all(SKILL_LEADS.map((value) => synthesis.skill(variable, value, cycle))), [variable, cycle]);

  const summary = skill.data?.status === "AVAILABLE" ? skill.data : null;
  const units = unitLabel(summary?.evaluation.units ?? (variable === "temperature" ? "C" : "m/s"));

  return <div className="page reliability">
    <div className="page-toolbar">
      <Segmented label="Variable" value={variable} onChange={setVariable} options={SKILL_VARIABLES} />
      <Segmented label="Lead time" value={lead} onChange={setLead} options={SKILL_LEADS.map((value) => ({ value, label: `+${value} h` }))} />
      <span className="toolbar-note">Weights are learned per 0.25° cell from recent cycles, smoothed over ±1°, and shrunk toward equal weights while history is short.</span>
    </div>

    {skill.status === "loading" && !skill.data && <Card><Loading label="Scoring GFS, IFS and AIFS on recent cycles…" detail="Replays past forecasts against analyses; the first run for a cycle can take about a minute." /></Card>}
    {skill.status === "error" && <Notice tone="error" title="Skill request failed" action={<button className="btn ghost" onClick={skill.reload}>Retry</button>}>{skill.error}</Notice>}
    {skill.data?.status === "UNAVAILABLE" && <Notice tone="warn" title="No weight map for this lead">{skill.data.reason}</Notice>}

    {summary && <>
      <section className="stat-row">
        <Stat label="AIRAVAT vs equal blend" value={signed(summary.evaluation.adaptive_vs_equal_pct, 1)} unit="% MAE" tone={summary.evaluation.adaptive_vs_equal_pct > 0 ? "good" : "warn"} detail={`${summary.evaluation.method}, ${plural(summary.sample_count, "cycle")}`} />
        {SOURCE_ORDER.filter((source) => summary.sources.includes(source)).map((source) => <Stat key={source} label={`${SOURCE_META[source].label} weight`} value={`${Math.round(summary.domain.mean_weight[source] * 100)}%`} detail={<>favoured over {Math.round(summary.domain.favoured_area_pct[source])}% of India · bias {signed(summary.domain.mean_bias[source], 2)} {units}</>} />)}
      </section>

      <Card eyebrow="MODEL WEIGHT MAPS" title={`Which model to trust where · ${SKILL_VARIABLES.find((item) => item.value === variable)?.label}, +${lead} h`} actions={<SourceLegend sources={summary.sources} />}>
        <div className="weight-maps">{summary.sources.map((source) => <WeightMap key={`${source}-${variable}-${lead}`} source={source} variable={variable} lead={lead} cycle={cycle} />)}</div>
        <p className="fine">Brighter = more weight. The three maps sum to 100% in every cell. Equal weighting would be {Math.round(100 / summary.sources.length)}% everywhere.</p>
      </Card>

      <div className="two-col">
        <Card eyebrow="BY REGION" title="Regional reliability">
          <table className="data-table">
            <thead><tr><th>Region</th><th>Weights</th><th>Lowest error</th>{summary.sources.map((source) => <th key={source} className="num">{SOURCE_META[source].short} MAE</th>)}</tr></thead>
            <tbody>{summary.regions.map((region) => <tr key={region.region}>
              <td>{region.label}</td>
              <td className="bar-cell"><WeightBar weights={region.weights} label={`${region.label} weights`} /></td>
              <td><SourceTag source={region.favoured} /></td>
              {summary.sources.map((source) => <td key={source} className={`num${region.favoured === source ? " strong" : ""}`}>{number(region.mae[source], 2)}</td>)}
            </tr>)}</tbody>
          </table>
          <p className="fine">MAE in {units} against the mean of the GFS and IFS 00 UTC analyses.</p>
        </Card>
        <Card eyebrow="IMPROVED SKILL?" title="Error by method">
          <SkillBars summary={summary} units={units} />
        </Card>
      </div>

      <div className="two-col">
        <Card eyebrow="LEAD-TIME DEPENDENCE" title="How the weights shift with lead time">
          {byLead.status === "loading" && !byLead.data ? <Loading label="Scoring other leads…" /> : <div className="lead-bars">
            {(byLead.data ?? []).map((item, index) => <div key={SKILL_LEADS[index]} className="lead-bar-row">
              <span className="lead-label">+{SKILL_LEADS[index]} h</span>
              {item.status === "AVAILABLE"
                ? <><WeightBar weights={item.domain.mean_weight} label={`Weights at +${SKILL_LEADS[index]} h`} /><span className="lead-meta">{plural(item.sample_count, "cycle")} · {signed(item.evaluation.adaptive_vs_equal_pct, 1)}% vs equal{item.sample_count < 2 ? " (in-sample)" : ""}</span></>
                : <span className="lead-meta unavailable">{item.reason?.includes("keeps about four days") ? "No verifiable history yet (ECMWF open data keeps ~4 days)" : item.reason}</span>}
            </div>)}
          </div>}
        </Card>
        <Card eyebrow="TRAINING DATA" title="Cycles behind these weights">
          <ul className="sample-list">
            {summary.samples.map((sample) => <li key={sample.initialization}><span className="ok-dot" />{cycleLabel(sample.initialization)} → verified {cycleLabel(sample.valid_time).replace(" · 00 UTC", "")}<em>{sample.sources.join(" · ")}</em></li>)}
            {summary.skipped.map((sample) => <li key={sample.initialization} className="skipped"><span className="skip-dot" />{cycleLabel(sample.initialization)}<em>{sample.reason.includes("404") ? "no longer on ECMWF open data" : sample.reason}</em></li>)}
          </ul>
          <p className="fine">Reference: {summary.evaluation.reference}. Smoothing {summary.smoothing}; shrinkage toward {summary.shrinkage.prior} with {summary.shrinkage.pseudo_samples} pseudo-cycles. History grows as the operational run archives each day's forecasts.</p>
        </Card>
      </div>
    </>}
  </div>;
}

function WeightMap({ source, variable, lead, cycle }: { source: SourceId; variable: VariableId; lead: number; cycle?: string }) {
  const field = useAsync(() => synthesis.field({ variable, lead, layer: "weights", weighting: "adaptive", source, initialization: cycle }), [source, variable, lead, cycle]);
  return <div className="weight-map">
    <SourceTag source={source} withKind />
    {field.status === "loading" && !field.data ? <Loading label="Loading map…" /> : <SpatialFieldMap field={field.data} title={`${SOURCE_META[source].label} weight`} palette={`weight_${source}`} scale="linear" mode="2d" compact />}
  </div>;
}

function SkillBars({ summary, units }: { summary: SkillSummary; units: string }) {
  const [reference, setReference] = useState<"mean" | "GFS" | "ECMWF">("mean");
  const table = summary.evaluation.by_reference[reference];
  const bars: MethodBar[] = [
    ...summary.sources.map((source) => ({ key: source, label: SOURCE_META[source].label, value: table[source], kind: "source" as const, source })),
    { key: "equal", label: "Equal-weight blend", value: table.equal, kind: "baseline" },
    { key: "weights_only", label: "Skill weights only", value: table.weights_only, kind: "baseline", note: "no bias correction" },
    { key: "adaptive", label: "AIRAVAT", value: table.adaptive, kind: "synthesis", note: "bias correction + skill weights" },
  ];
  return <>
    <Segmented size="small" label="Reference" value={reference} onChange={setReference} options={REFERENCES.map((item) => ({ value: item.key, label: item.key === "mean" ? "Mean analysis" : `${item.key === "ECMWF" ? "IFS" : "GFS"} analysis` }))} />
    <MethodBars bars={bars} units={units} caption={`Mean absolute error over India, ${summary.evaluation.method}. Lower is better. Reference: ${REFERENCES.find((item) => item.key === reference)?.label}.`} />
    <Notice tone="info" title="Read this honestly">{summary.evaluation.caveat}</Notice>
  </>;
}

