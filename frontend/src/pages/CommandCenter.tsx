import { ArrowRight, BrainCircuit, CloudDownload, Gauge, Grid3x3, Layers, ScanSearch, ShieldAlert, SlidersHorizontal, Workflow } from "lucide-react";
import { synthesis } from "../api";
import { useApp } from "../app/context";
import { WeightBar } from "../components/charts";
import { Card, LevelChip, Loading, Notice, SourceTag, Stat, StatusDot } from "../components/ui";
import { SOURCE_META, SOURCE_ORDER, area, coordinate, cycleLabel, istTime, number, signed, watchSignal } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import type { Extremes, SkillSummary } from "../types/synthesis";

const PIPELINE = [
  { icon: CloudDownload, title: "Ingest", text: "GFS · IFS · AIFS GRIB2 for the 00 UTC cycle" },
  { icon: Grid3x3, title: "Normalise", text: "0.25° India grid, common units, no interpolation" },
  { icon: ScanSearch, title: "Score skill", text: "Replay recent cycles against analyses" },
  { icon: SlidersHorizontal, title: "Bias + weights", text: "Per-cell bias correction, inverse-MAE weights" },
  { icon: Layers, title: "Blend", text: "Adaptive multi-model field per variable and lead" },
  { icon: ShieldAlert, title: "Extremes", text: "Heavy rain, heat, wind with model agreement" },
];

export function CommandCenter() {
  const { catalog, cycle, navigate } = useApp();
  const selectedCycle = cycle ?? catalog?.cycles.find((item) => item.complete)?.initialization;
  const cycleInfo = catalog?.cycles.find((item) => item.initialization === selectedCycle);
  const skill = useAsync(() => Promise.all([synthesis.skill("temperature", 24, cycle), synthesis.skill("wind_speed", 24, cycle)]), [cycle]);
  const outlook = useAsync(() => Promise.all([0, 1, 2].map((day) => synthesis.extremes(day, cycle))), [cycle]);
  const runs = useAsync(() => synthesis.runs(), []);
  const [temperature, wind] = skill.data ?? [];
  const lastRun = runs.data?.[0];
  const signals = (outlook.data ?? []).flatMap((day) => (day.hazards ?? []).filter((hazard) => hazard.highest_level).map((hazard) => ({ day: day.day, hazard })));
  const watches = (outlook.data ?? []).flatMap((day) => (day.hazards ?? []).filter((hazard) => !hazard.highest_level && watchSignal(hazard.agreement)).map((hazard) => ({ day: day.day, hazard })));
  const dayName = (day: number) => (day === 0 ? "today" : `D+${day}`);

  return <div className="page command">
    <section className="hero">
      <div className="hero-copy">
        <span className="eyebrow">HYBRID AI–NWP MULTI-MODEL BLENDING · INDIA</span>
        <h1>One forecast from three models, weighted by where each one earns trust.</h1>
        <p>AIRAVAT pulls live NOAA GFS, ECMWF IFS and ECMWF's AI model AIFS, learns each model's regional bias and skill from recent cycles, and issues an adaptive blend with extreme-weather guidance.</p>
        <div className="hero-actions">
          <button className="btn primary" onClick={() => navigate("explorer")}>Open blend explorer <ArrowRight size={15} /></button>
          <button className="btn ghost" onClick={() => navigate("reliability")}>See weight maps</button>
          <button className="btn ghost" onClick={() => navigate("extremes")}>Extreme weather</button>
        </div>
      </div>
      <div className="hero-sources">
        <span className="eyebrow">CYCLE {cycleLabel(selectedCycle)}</span>
        {SOURCE_ORDER.map((source) => {
          const meta = catalog?.sources.find((item) => item.id === source);
          const available = cycleInfo?.sources?.[source];
          return <div key={source} className="source-card">
            <div className="source-card-head"><SourceTag source={source} /><em>{SOURCE_META[source].kind}{source === "AIFS" ? <BrainCircuit size={13} /> : null}</em></div>
            <strong>{SOURCE_META[source].label}</strong>
            <div className="source-card-foot">
              <StatusDot ok={meta ? (meta.enabled ? (available ?? null) : false) : null} label={!meta ? "checking" : !meta.enabled ? "disabled" : available ? "cycle available" : available === false ? "not published yet" : "unknown"} />
              {temperature?.status === "AVAILABLE" && temperature.domain.mean_weight[source] !== undefined && <span className="weight-inline">{Math.round(temperature.domain.mean_weight[source] * 100)}% weight</span>}
            </div>
          </div>;
        })}
      </div>
    </section>

    <section className="stat-row">
      <SkillStat label="Temperature blend vs equal weights" summary={temperature} loading={skill.status === "loading"} />
      <SkillStat label="Wind blend vs equal weights" summary={wind} loading={skill.status === "loading"} />
      <Stat label="Hazard signals, next 3 days" value={outlook.status === "loading" ? "…" : String(signals.length)} detail={signals.length ? signals.map((item) => `${item.hazard.label} (${dayName(item.day)})`).join(" · ") : watches.length ? `Blend below thresholds; single-model watch: ${watches.map((item) => `${item.hazard.label} ${dayName(item.day)}`).join(", ")}` : "No model crosses a warning threshold"} tone={signals.length || watches.length ? "warn" : "good"} />
      <Stat label="Last operational run" value={lastRun ? { complete: "Complete", complete_with_issues: "With issues", failed: "Failed", running: "Running", queued: "Queued", interrupted: "Interrupted" }[lastRun.status] : "None yet"} detail={lastRun ? `${cycleLabel(lastRun.initialization)} · ${istTime(lastRun.finished_at ?? lastRun.created_at)}` : "Start one on the Operations page"} tone={lastRun?.status === "complete" ? "good" : lastRun ? "warn" : "muted"} />
    </section>

    <Card eyebrow="PIPELINE" title="From raw model output to blended guidance" actions={<button className="btn ghost small" onClick={() => navigate("operations")}><Workflow size={14} /> Operations</button>}>
      <ol className="pipeline">{PIPELINE.map((step, index) => <li key={step.title}><span className="step-index">{String(index + 1).padStart(2, "0")}</span><step.icon size={18} /><strong>{step.title}</strong><p>{step.text}</p></li>)}</ol>
    </Card>

    <div className="two-col wide-left">
      <Card eyebrow="EXTREME-WEATHER OUTLOOK" title="Next three days" actions={<button className="btn ghost small" onClick={() => navigate("extremes")}>Details <ArrowRight size={14} /></button>}>
        {outlook.status === "loading" && !outlook.data ? <Loading label="Scanning models for hazards…" /> : outlook.status === "error" ? <Notice tone="error" title="Outlook unavailable">{outlook.error}</Notice> : <OutlookTable days={outlook.data ?? []} />}
      </Card>
      <Card eyebrow="WHERE EACH MODEL WINS" title="Temperature weights by region, +24 h" actions={<button className="btn ghost small" onClick={() => navigate("reliability")}><Gauge size={14} /> Skill</button>}>
        {skill.status === "loading" && !skill.data ? <Loading label="Scoring models…" detail="First run for a cycle takes about a minute." /> : temperature?.status === "AVAILABLE"
          ? <div className="region-bars">{temperature.regions.map((region) => <div key={region.region} className="region-bar"><span>{region.label}</span><WeightBar weights={region.weights} label={region.label} /></div>)}</div>
          : <Notice tone="warn" title="Weights unavailable">{temperature?.reason ?? skill.error}</Notice>}
      </Card>
    </div>
  </div>;
}

function SkillStat({ label, summary, loading }: { label: string; summary?: SkillSummary; loading: boolean }) {
  if (loading && !summary) return <Stat label={label} value="…" detail="Scoring recent cycles" />;
  if (!summary || summary.status !== "AVAILABLE") return <Stat label={label} value="—" detail={summary?.reason ?? "unavailable"} tone="muted" />;
  const gain = summary.evaluation.adaptive_vs_equal_pct;
  return <Stat label={label} value={signed(gain, 1)} unit="% error" tone={gain > 0 ? "good" : "warn"} detail={`MAE ${number(summary.evaluation.mae.adaptive, 2)} vs ${number(summary.evaluation.mae.equal, 2)}, ${summary.sample_count}-cycle leave-one-out`} />;
}

function OutlookTable({ days }: { days: Extremes[] }) {
  const hazards = days[0]?.hazards?.map((hazard) => ({ id: hazard.hazard, label: hazard.label })) ?? [];
  return <table className="data-table outlook">
    <thead><tr><th>Hazard</th>{days.map((day) => <th key={day.day}>{day.day === 0 ? "Today" : `D+${day.day}`}<small>{day.date?.slice(5)}</small></th>)}</tr></thead>
    <tbody>{hazards.map((row) => <tr key={row.id}>
      <td>{row.label}</td>
      {days.map((day) => {
        const hazard = day.hazards?.find((item) => item.hazard === row.id);
        if (!hazard || hazard.status !== "AVAILABLE") return <td key={day.day} className="muted-text">n/a</td>;
        return <td key={day.day}>
          <LevelChip level={hazard.highest_level} levels={hazard.levels?.map((level) => level.label) ?? []} watch={hazard.highest_level ? null : watchSignal(hazard.agreement)} />
          <small className="cell-note">blend peak {number(hazard.peak?.value)} {hazard.units}{hazard.peak && (hazard.highest_level || hazard.agreement?.some_models_km2) ? ` · ${coordinate(hazard.peak.latitude, hazard.peak.longitude)}` : ""}{hazard.agreement?.all_models_km2 ? ` · all models agree on ${area(hazard.agreement.all_models_km2)}` : ""}{!hazard.highest_level && watchSignal(hazard.agreement) ? ` · ${watchSignal(hazard.agreement)}` : ""}</small>
        </td>;
      })}
    </tr>)}</tbody>
  </table>;
}
