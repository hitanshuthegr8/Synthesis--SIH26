import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleDashed, Play, TerminalSquare, XCircle } from "lucide-react";
import { ApiError, synthesis } from "../api";
import { useApp } from "../app/context";
import { Progress } from "../components/charts";
import { Card, Field, Notice } from "../components/ui";
import { VARIABLE_META, cycleLabel, istTime, signed } from "../lib/format";
import type { OperationalRun, VariableId } from "../types/synthesis";

const STATUS_ICON = { complete: CheckCircle2, warning: AlertTriangle, unavailable: CircleDashed, failed: XCircle };

export function Operations() {
  const { cycle, catalog } = useApp();
  const [variables, setVariables] = useState<VariableId[]>(["temperature", "precipitation", "wind_speed"]);
  const [leads, setLeads] = useState<number[]>([24, 48, 72]);
  const [days, setDays] = useState<number[]>([0, 1, 2]);
  const [runs, setRuns] = useState<OperationalRun[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const refresh = () => synthesis.runs().then((list) => {
    setRuns(list);
    setActiveId((current) => current ?? list[0]?.run_id ?? null);
  }).catch(() => undefined);
  useEffect(() => { void refresh(); }, []);
  const active = runs.find((run) => run.run_id === activeId) ?? null;
  const running = runs.some((run) => run.status === "queued" || run.status === "running");
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [running]);

  const toggle = <T,>(list: T[], value: T) => list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const run = await synthesis.startRun({ initialization: cycle, variables, leads: [...leads].sort((a, b) => a - b), days: [...days].sort() });
      setActiveId(run.run_id);
      await refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not start the run");
    } finally {
      setStarting(false);
    }
  };
  const steps = variables.length * leads.length + days.length;

  return <div className="page operations">
    <div className="two-col wide-right">
      <Card eyebrow="ROUTINE BLENDING" title="Run the workflow">
        <p className="muted-text">One run fetches every model for the cycle, re-scores skill, bias-corrects and blends each variable and lead, then issues extreme-weather guidance. Products are written as JSON under <code>backend/data/products/</code>.</p>
        <Field label="Cycle"><div className="readonly">{cycle ? cycleLabel(cycle) : `Latest complete (${cycleLabel(catalog?.cycles.find((item) => item.complete)?.initialization)})`}</div></Field>
        <Field label="Variables">
          <div className="chip-set">{(Object.keys(VARIABLE_META) as VariableId[]).map((id) => <button key={id} className={`chip ${variables.includes(id) ? "on" : ""}`} onClick={() => setVariables(toggle(variables, id))}>{VARIABLE_META[id].short}</button>)}</div>
        </Field>
        <Field label="Lead times (h)">
          <div className="chip-set">{[12, 24, 36, 48, 72, 96, 120].map((value) => <button key={value} className={`chip ${leads.includes(value) ? "on" : ""}`} onClick={() => setLeads(toggle(leads, value))}>{value}</button>)}</div>
        </Field>
        <Field label="Extreme-guidance days">
          <div className="chip-set">{[0, 1, 2, 3, 4].map((value) => <button key={value} className={`chip ${days.includes(value) ? "on" : ""}`} onClick={() => setDays(toggle(days, value))}>{value === 0 ? "Today" : `D+${value}`}</button>)}</div>
        </Field>
        <button className="btn primary" disabled={starting || running || !variables.length || !leads.length} onClick={start}><Play size={15} />{running ? "A run is in progress" : `Start run · ${steps} steps`}</button>
        {error && <Notice tone="error" title="Run not started">{error}</Notice>}
        <div className="cli">
          <span className="eyebrow"><TerminalSquare size={12} /> SCHEDULE IT (cron / Task Scheduler)</span>
          <pre>{`backend\\venv\\Scripts\\python scripts\\run_operational_blend.py ^
  --variables ${variables.join(" ")} ^
  --leads ${[...leads].sort((a, b) => a - b).join(" ")} --days ${[...days].sort().join(" ")}`}</pre>
          <p className="fine">Run daily after ~08:00 UTC, when both the GFS and ECMWF 00 UTC cycles are published. Each run also archives that day's forecasts, which lengthens the skill history.</p>
        </div>
      </Card>

      <Card eyebrow={active ? active.run_id : "NO RUNS YET"} title={active ? <RunTitle run={active} /> : "Run log"}>
        {active ? <>
          <Progress value={active.completed_steps} total={active.total_steps} />
          <p className="muted-text">{Math.min(active.completed_steps, active.total_steps)} of {active.total_steps} steps · cycle {cycleLabel(active.initialization)} · started {istTime(active.started_at ?? active.created_at)}{active.finished_at ? ` · finished ${istTime(active.finished_at)}` : ""}</p>
          <ol className="run-log">{active.log.map((entry, index) => {
            const Icon = STATUS_ICON[entry.status];
            return <li key={index} className={entry.status}><Icon size={14} /><strong>{entry.stage}</strong><span>{entry.message}</span></li>;
          })}{(active.status === "running" || active.status === "queued") && <li className="pending"><CircleDashed size={14} className="spin" /><strong>working…</strong></li>}</ol>
          {active.products.length > 0 && <>
            <span className="eyebrow">PRODUCTS</span>
            <table className="data-table compact">
              <thead><tr><th>Product</th><th>Weighting</th><th className="num">vs equal</th><th>Flags</th></tr></thead>
              <tbody>{active.products.map((product) => <tr key={product.path}>
                <td>{product.name}</td>
                <td>{product.weighting ?? "—"}</td>
                <td className="num">{product.adaptive_vs_equal_pct !== undefined && product.adaptive_vs_equal_pct !== null ? `${signed(product.adaptive_vs_equal_pct, 1)}%${product.skill_samples === 1 ? " (in-sample)" : ""}` : "—"}</td>
                <td>{product.flags?.length ? product.flags.join(", ") : product.flags ? "none" : ""}{product.watch?.length ? <span className="watch-inline"> · watch: {product.watch.join(", ")}</span> : null}</td>
              </tr>)}</tbody>
            </table>
          </>}
        </> : <p className="muted-text">Start a run to see each step's outcome here.</p>}
        {runs.length > 1 && <div className="history">
          <span className="eyebrow">HISTORY</span>
          {runs.map((run) => <button key={run.run_id} className={`history-row ${run.run_id === activeId ? "active" : ""}`} onClick={() => setActiveId(run.run_id)}>
            <RunTitle run={run} /><em>{istTime(run.created_at)}</em>
          </button>)}
        </div>}
      </Card>
    </div>
  </div>;
}

function RunTitle({ run }: { run: OperationalRun }) {
  const label = { queued: "Queued", running: "Running", complete: "Complete", complete_with_issues: "Complete with issues", failed: "Failed", interrupted: "Interrupted (backend restarted)" }[run.status];
  return <span className={`run-status ${run.status}`}>{label}</span>;
}
