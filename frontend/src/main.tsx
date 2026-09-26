import { useState, useEffect, useCallback, useMemo, useRef, type ReactNode } from "react";
import * as echarts from "echarts";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertCircle, AlertTriangle, ArrowRight, BrainCircuit, CheckCircle2, ChevronDown,
  CloudSun, Database, Download, FlaskConical, LayoutDashboard, Play, RefreshCw,
  MapPinned, Search, Server, ShieldCheck, TrendingUp, Wind, X, Zap,
} from "lucide-react";
import "./styles.css";
import { SpatialFieldMap } from "./components/SpatialFieldMap";
import type { SpatialFieldResponse } from "./types/api";

// ── Types ────────────────────────────────────────────────────────────────────

type Forecast = { model_id: string; value: number; unit: string };

type Disagreement = {
  level: string; range: number; std: number; model_count: number;
  mean: number; min_value: number; max_value: number;
};

type Blend = {
  variable: string; blended_value: number; lower_bound: number; upper_bound: number;
  model_weights: Record<string, number>;
  disagreement: Disagreement;
  regime: string; regime_confidence: number;
  explanation: string[]; run_id: string; processing_time_ms: number;
  algorithm: string; verification_dataset: string;
  fallback_mode: boolean; cycle_time?: string | null; region?: string;
  dataset_version?: string; configuration_hash?: string;
};

type Reliability = { model_id: string; score: number; sample_count: number; metric: string };

type Verification = {
  run_id: string; forecast_value: number; observation_value: number;
  error: number; absolute_error: number;
  model_errors: Record<string, number>; lead_hours: number; regime?: string;
};

type AutopsyEntry = {
  run_id: string; variable: string; valid_time: string;
  forecast_value: number; observation_value: number; blend_error: number;
  model_forecasts: Record<string, number>; model_errors: Record<string, number>;
  regime?: string; assessment: string;
};

type ComputationStep = { name: string; status: string; duration_ms: number; details: string[] };

type Trace = {
  run_id: string; status: string; duration_ms: number; scenario: string;
  variable: string; lead_hours: number; region: string; dataset_version: string;
  algorithm_version?: string; configuration_hash?: string;
  source_availability: Record<string, boolean>;
  steps: ComputationStep[];
  stale_from_run_id?: string;
};

type PipelineResponse = {
  run_id: string; status: string;
  forecasts: Forecast[]; reliability: Reliability[];
  blend: Blend; verification: Verification;
  autopsy: AutopsyEntry; trace: Trace;
};

type SourceHealth = {
  source_id: string; status: string; mode: string; message: string;
};

type DemoManifest = {
  dataset_version: string; generation_seed: number; created_at: string; scenario: string;
  file_hashes: Record<string, string>; integrity: string; source_mode: string;
};

type SystemStatus = {
  api: string; database: string; pipeline: string; demo_mode: boolean;
  source_adapters: SourceHealth[];
  last_cycle_run_id: string | null; last_successful_cycle: string | null;
  last_processing_time_ms: number | null;
};

// ── Config ───────────────────────────────────────────────────────────────────

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const SCENARIOS: Record<string, { label: string; variable: string; description: string }> = {
  normal: { label: "Normal", variable: "temperature", description: "Models agree closely. Low disagreement, similar weights." },
  heavy_rain: { label: "Heavy Rain", variable: "precipitation", description: "HEAVY_RAIN regime. High disagreement. AI+ECMWF gain weight." },
  model_disagreement: { label: "Model Disagreement", variable: "precipitation", description: "EXTREME disagreement. Uncertainty widens significantly." },
  model_failure: { label: "Model Failure", variable: "precipitation", description: "GFS anomalous. Weight penalty applied. Blend shifts." },
};

const VAR_LABELS: Record<string, string> = { temperature: "Temperature", precipitation: "Precipitation", wind_speed: "Wind Speed" };
const VAR_UNITS: Record<string, string> = { temperature: "°C", precipitation: "mm", wind_speed: "m/s" };
const LEADS = [24, 48, 72, 96, 120, 144, 168];
const PAGES = ["overview", "forecast-detail", "pipeline", "model-analysis", "reliability-map", "verification", "autopsy", "system"] as const;
type Page = typeof PAGES[number];
const PAGE_LABELS: Record<Page, string> = {
  overview: "Overview",
  "forecast-detail": "Forecast Detail",
  pipeline: "Data Pipeline",
  "model-analysis": "Model Analysis",
  "reliability-map": "Reliability Map",
  verification: "Verification",
  autopsy: "Forecast Autopsy",
  system: "System Status",
};
const PAGE_ICONS: Record<Page, ReactNode> = {
  overview: <LayoutDashboard size={15} />,
  "forecast-detail": <CloudSun size={15} />,
  pipeline: <Database size={15} />,
  "model-analysis": <TrendingUp size={15} />,
  "reliability-map": <TrendingUp size={15} />,
  verification: <FlaskConical size={15} />,
  autopsy: <Search size={15} />,
  system: <Server size={15} />,
};

type ModelSkillRow = {
  model_id: string; variable: string; lead_hours: number; metric: string;
  score: number; sample_count: number; region?: string; regime?: string | null;
};

type ReliabilityGrid = {
  variable: string; lead_hours: number; metric: string; dataset_version: string; mode: string;
  latitude_count: number; longitude_count: number; resolution_degrees: number;
  latitudes: number[]; longitudes: number[]; points: [number, number, number][];
  india_focus: { min_lat: number; max_lat: number; min_lon: number; max_lon: number };
};

// ── API helpers ──────────────────────────────────────────────────────────────

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!r.ok) {
    const payload = await r.json().catch(() => null) as { detail?: { error?: { message?: string } } } | null;
    throw new Error(payload?.detail?.error?.message ?? `${r.status}: ${r.statusText}`);
  }
  return r.json() as Promise<T>;
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status}: ${r.statusText}`);
  return r.json() as Promise<T>;
}

function shortHash(value?: string | null, length = 12): string {
  if (!value) return "—";
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

function formatUtc(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toUTCString();
}

// ── Shared primitive components ──────────────────────────────────────────────

function Panel({ title, sub, children, action }: {
  title: string; sub?: string; children: ReactNode; action?: ReactNode;
}) {
  return (
    <div className="panel">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">{title}</h2>
          {sub && <p className="panel-sub">{sub}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function Badge({ level }: { level: string }) {
  const cls = level === "LOW" ? "badge-low"
    : level === "MEDIUM" ? "badge-med"
    : level === "HIGH" ? "badge-high"
    : "badge-extreme";
  return <span className={`badge ${cls}`}>{level}</span>;
}

function Spinner() {
  return <div className="spinner" aria-label="Loading" />;
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="error-box" role="alert">
      <AlertCircle size={16} /> {message}
    </div>
  );
}

function WeightBar({ model, weight, unit, value }: { model: string; weight: number; unit: string; value?: number }) {
  return (
    <div className="weight-row">
      <div className="weight-row-meta">
        <span className="model-tag">{model.toUpperCase()}</span>
        <span className="weight-pct">{Math.round(weight * 100)}%</span>
        {value !== undefined && <span className="weight-val">{value.toFixed(1)} {unit}</span>}
      </div>
      <div className="weight-track">
        <div className="weight-fill" style={{ width: `${weight * 100}%` }} />
      </div>
    </div>
  );
}

function StepBadge({ status }: { status: string }) {
  if (status === "complete") return <CheckCircle2 size={14} className="step-ok" />;
  if (status === "failed") return <AlertTriangle size={14} className="step-err" />;
  return <Activity size={14} className="step-pend" />;
}

function RunHealthStrip({ result }: { result: PipelineResponse }) {
  const available = Object.values(result.trace.source_availability).filter(Boolean).length;
  const state = result.status.toUpperCase();
  const detail = result.status === "stale"
    ? `STALE LAST-GOOD FORECAST from ${result.trace.stale_from_run_id ?? "a prior run"}`
    : result.status === "degraded"
      ? `DEGRADED SOURCE SET · ${available}/4 sources validated · uncertainty widened`
      : `FRESH CYCLE · ${available}/4 sources validated`;
  return (
    <div className={`run-health ${result.status}`}>
      {result.status === "complete" ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
      <strong>{state}</strong><span>{detail}</span>
    </div>
  );
}

// ── Overview Page ────────────────────────────────────────────────────────────

function OverviewPage() {
  const [scenario, setScenario] = useState("heavy_rain");
  const [lead, setLead] = useState(24);
  const [result, setResult] = useState<PipelineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [traceOpen, setTraceOpen] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState<number | null>(null);
  const [manifest, setManifest] = useState<DemoManifest | null>(null);

  useEffect(() => {
    getJson<DemoManifest>("/api/demo/manifest").then(setManifest).catch(() => setManifest(null));
  }, []);

  const exportDossier = useCallback(async () => {
    if (!result?.run_id) return;
    try {
      const dossier = await getJson<PipelineResponse>(`/api/runs/${result.run_id}/dossier`);
      const blob = new Blob([JSON.stringify(dossier, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `synthesis-dossier-${result.run_id}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dossier export failed.");
    }
  }, [result?.run_id]);

  const runCycle = useCallback(async (autoRun = false) => {
    setLoading(true); setError("");
    if (!autoRun) {
      setAnalysisProgress(0);
      const steps = 7;
      for (let i = 1; i <= steps; i++) {
        await new Promise(r => setTimeout(r, 250));
        setAnalysisProgress(i);
      }
    }
    try {
      const data = await postJson<PipelineResponse>("/api/pipeline/run", { scenario, lead_hours: lead });
      setResult(data);
      if (!autoRun) setTraceOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Forecast cycle failed.");
    } finally {
      setLoading(false);
      setTimeout(() => setAnalysisProgress(null), 600);
    }
  }, [scenario, lead]);

  // auto-load on scenario/lead change
  useEffect(() => { void runCycle(true); }, [scenario, lead]);

  const b = result?.blend;
  const unit = b ? VAR_UNITS[b.variable] ?? "" : "";
  const fcs = result?.forecasts ?? [];

  const ANALYSIS_STEPS = [
    "Ingesting source forecasts",
    "Validating & normalising data",
    "Loading historical skill records",
    "Detecting weather regime",
    "Measuring model disagreement",
    "Calculating adaptive weights",
    "Generating blended forecast",
  ];

  return (
    <>
      {/* Controls */}
      <div className="toolbar">
        <div>
          <p className="eyebrow">SYNTHESIS — Adaptive Forecast Console</p>
          <h1>{b ? VAR_LABELS[b.variable] : "Forecast"} outlook — {lead}h lead time</h1>
        </div>
        <div className="controls">
          <button className="run-btn" onClick={() => void runCycle(false)} disabled={loading || analysisProgress !== null}>
            <Play size={14} /> {loading ? "Running…" : "Run Forecast Cycle"}
          </button>
          {result?.run_id && (
            <button className="icon-btn" type="button" onClick={() => void exportDossier()} title="Export Forecast Dossier" aria-label="Export Forecast Dossier">
              <Download size={16} />
            </button>
          )}
          <label>Scenario
            <select value={scenario} onChange={e => { setScenario(e.target.value); }}>
              {Object.entries(SCENARIOS).map(([k, v]) => (
                <option key={k} value={k}>{v.label}</option>
              ))}
            </select>
            <ChevronDown size={13} />
          </label>
          <label>Lead time
            <select value={lead} onChange={e => setLead(Number(e.target.value))}>
              {LEADS.map(l => <option key={l} value={l}>{l}h</option>)}
            </select>
            <ChevronDown size={13} />
          </label>
          <button className="icon-btn" onClick={() => void runCycle(true)} title="Refresh"><RefreshCw size={16} /></button>
        </div>
      </div>

      {SCENARIOS[scenario] && (
        <div className="scenario-banner">
          <AlertTriangle size={13} /> <strong>{SCENARIOS[scenario].label}:</strong> {SCENARIOS[scenario].description}
        </div>
      )}

      {error && <ErrorBox message={error} />}

      {loading && !result && (
        <div className="loading-block"><Spinner /> Loading forecast cycle…</div>
      )}

      {b && (
        <div className="dashboard">
          <RunHealthStrip result={result} />
          {/* Hero band */}
          <div className="hero-band">
            <div className="hero-forecast">
              <p className="eyebrow">SYNTHESIS Weighted Forecast</p>
              <div className="big-value">{b.blended_value.toFixed(1)}<span>{unit}</span></div>
              <p className="hero-sub">{lead}h outlook · {b.region ?? "Maharashtra"} · {b.regime.replace(/_/g, " ")}</p>
              {b.fallback_mode && <div className="fallback-warning">⚠ SINGLE SOURCE FALLBACK — confidence reduced</div>}
            </div>
            <div className="hero-range">
              <p className="eyebrow">Forecast Uncertainty Range</p>
              <p className="range-vals">{b.lower_bound.toFixed(1)} – {b.upper_bound.toFixed(1)} <span>{unit}</span></p>
              <div className="range-bar">
                <div className="range-fill" />
                <div className="range-dot" />
              </div>
              <p className="range-note">Not a calibrated confidence interval</p>
            </div>
            <div className="hero-regime">
              <p className="eyebrow">Regime Classification</p>
              <strong className="regime-name">{b.regime.replace(/_/g, " ")}</strong>
              <p className="regime-conf">Rule score: {Math.round(b.regime_confidence * 100)}%</p>
            </div>
            <div className="hero-disagree">
              <p className="eyebrow">Model Disagreement</p>
              <Badge level={b.disagreement.level} />
              <p className="disagree-range">Range: {b.disagreement.min_value.toFixed(1)}–{b.disagreement.max_value.toFixed(1)} {unit}</p>
              <p className="disagree-spread">Spread (σ): {b.disagreement.std.toFixed(2)} {unit}</p>
            </div>
          </div>

          {/* Middle grid */}
          <div className="mid-grid">
            <Panel title="What The Models See" sub="Demo scenario inputs">
              <div className="source-list">
                {fcs.map(f => (
                  <div key={f.model_id} className="source-row">
                    <span className="model-tag">{f.model_id.toUpperCase()}</span>
                    <strong>{f.value.toFixed(1)} {unit}</strong>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="Adaptive Model Weights" sub={`Algorithm: ${b.algorithm}`}>
              <div className="weights-list">
                {Object.entries(b.model_weights).sort((a, b) => b[1] - a[1]).map(([m, w]) => {
                  const fc = fcs.find(f => f.model_id === m);
                  return <WeightBar key={m} model={m} weight={w} unit={unit} value={fc?.value} />;
                })}
              </div>
            </Panel>

            <Panel title="Historical Reliability" sub={b.verification_dataset}>
              <table className="rel-table">
                <thead><tr><th>Model</th><th>MAE</th><th>Cases</th></tr></thead>
                <tbody>
                  {(result?.reliability ?? []).filter(r => r.metric === "mae").map(r => (
                    <tr key={r.model_id}>
                      <td><span className="model-tag">{r.model_id.toUpperCase()}</span></td>
                      <td>{r.score.toFixed(2)} {unit}</td>
                      <td>{r.sample_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          </div>

          {/* Bottom grid */}
          <div className="bot-grid">
            <Panel
              title="Why This Blend?"
              action={<button className="text-btn" onClick={() => setTraceOpen(true)}>View computation trace →</button>}
            >
              <ol className="explanation-list">
                {b.explanation.map((e, i) => <li key={i}>{e}</li>)}
              </ol>
            </Panel>

            <Panel title="Forecast Autopsy" sub="Synthetic verification observation">
              {result?.verification && (
                <div className="autopsy-mini">
                  <div><span>Prediction</span><strong>{result.verification.forecast_value.toFixed(1)} {unit}</strong></div>
                  <div><span>Observation</span><strong>{result.verification.observation_value.toFixed(1)} {unit}</strong></div>
                  <div><span>Error</span><strong>{result.verification.error.toFixed(1)} {unit}</strong></div>
                  <div><span>Abs. Error</span><strong>{result.verification.absolute_error.toFixed(1)} {unit}</strong></div>
                </div>
              )}
            </Panel>
          </div>

          {manifest && (
            <Panel
              title="How SYNTHESIS Builds This Forecast"
              sub="A clear path from model signals to a decision-ready outlook"
              action={<span className="integrity-chip"><CheckCircle2 size={13} /> DEMO CHECKED</span>}
            >
              <div className="lineage-flow" aria-label="Forecast data lineage">
                <div className="lineage-node">
                  <Database size={18} />
                  <strong>Model signals</strong>
                  <span>Four independent forecast views</span>
                </div>
                <div className="lineage-arrow" aria-hidden="true">→</div>
                <div className="lineage-node">
                  <ShieldCheck size={18} />
                  <strong>Clean & check</strong>
                  <span>Catch missing, repeated, or implausible values</span>
                </div>
                <div className="lineage-arrow" aria-hidden="true">→</div>
                <div className="lineage-node">
                  <Activity size={18} />
                  <strong>Learn from outcomes</strong>
                  <span>Compare each model against prior cases</span>
                </div>
                <div className="lineage-arrow" aria-hidden="true">→</div>
                <div className="lineage-node emphasis">
                  <Zap size={18} />
                  <strong>Make the blend</strong>
                  <span>Give more influence to the best-fitting signals</span>
                </div>
              </div>
              <div className="lineage-facts">
                <span><strong>4</strong> model perspectives</span>
                <span><strong>{Object.keys(manifest.file_hashes).length}</strong> checked data files</span>
                <span>Repeatable demo run</span>
                <span>Created {formatUtc(manifest.created_at)}</span>
              </div>
              <p className="lineage-note">
                This is a repeatable demo using locally generated scenarios, so it can be shown reliably without internet access. It demonstrates the full decision flow; it is not presented as a live weather warning service.
              </p>
            </Panel>
          )}

          {/* Provenance bar */}
          <div className="provenance-bar">
            <span>RUN: {b.run_id}</span>
            <span>Cycle: {formatUtc(b.cycle_time)}</span>
            <span>Sources: {fcs.length}/4</span>
            <span>Dataset: {b.dataset_version ?? "demo-v1"}</span>
            <span>Config: {shortHash(b.configuration_hash ?? result?.trace.configuration_hash)}</span>
            <span>Time: {b.processing_time_ms}ms</span>
          </div>
        </div>
      )}

      {/* Analysis progress overlay */}
      {analysisProgress !== null && (
        <div className="analysis-overlay">
          <div className="analysis-card">
            <p className="eyebrow">SYNTHESIS ANALYSIS</p>
            {ANALYSIS_STEPS.map((step, i) => (
              <div key={step} className={`analysis-step ${i < analysisProgress ? "done" : i === analysisProgress ? "active" : "pending"}`}>
                {i < analysisProgress ? <CheckCircle2 size={14} /> : <i />}
                {step}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Trace drawer */}
      {traceOpen && result && (
        <TraceDrawer result={result} unit={unit} onClose={() => setTraceOpen(false)} />
      )}
    </>
  );
}

// ── Trace Drawer ──────────────────────────────────────────────────────────────

function TraceDrawer({ result, unit, onClose }: { result: PipelineResponse; unit: string; onClose: () => void }) {
  const { blend: b, forecasts: fcs, reliability, trace } = result;
  const weights = Object.entries(b.model_weights).sort((a, x) => x[1] - a[1]);
  const maes = Object.fromEntries(reliability.filter(r => r.metric === "mae").map(r => [r.model_id, r.score]));

  return (
    <div className="drawer-overlay" role="dialog" aria-modal aria-label="Computation trace">
      <aside className="drawer">
        <header className="drawer-header">
          <div>
            <p className="eyebrow">SYNTHESIS COMPUTATION TRACE</p>
            <strong className="mono">{b.run_id}</strong>
          </div>
          <button onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <p className="drawer-meta">{trace.lead_hours}h {b.variable} · {b.region} · {b.dataset_version}</p>

        {trace.steps.map((step, i) => (
          <section key={step.name} className="trace-step">
            <h3><StepBadge status={step.status} /> Step {i + 1} — {step.name.replace(/_/g, " ")} <span className="trace-ms">{step.duration_ms}ms</span></h3>
            <ul>{step.details.map((d, j) => <li key={j}>{d}</li>)}</ul>
          </section>
        ))}

        <section className="trace-step">
          <h3><CheckCircle2 size={14} className="step-ok" /> Computation detail — Weighted blend</h3>
          <div className="trace-table">
            <div className="trace-row trace-head"><span>Model</span><span>Forecast</span><span>MAE</span><span>Weight</span><span>Contribution</span></div>
            {weights.map(([m, w]) => {
              const fc = fcs.find(f => f.model_id === m);
              return (
                <div key={m} className="trace-row">
                  <span className="model-tag">{m.toUpperCase()}</span>
                  <span>{fc?.value.toFixed(1) ?? "—"} {unit}</span>
                  <span>{maes[m]?.toFixed(2) ?? "—"} {unit}</span>
                  <span>{Math.round(w * 100)}%</span>
                  <span>{((fc?.value ?? 0) * w).toFixed(2)} {unit}</span>
                </div>
              );
            })}
            <div className="trace-row trace-total">
              <span>SYNTHESIS</span><span /><span /><span>100%</span>
              <span className="blend-result">{b.blended_value.toFixed(2)} {unit}</span>
            </div>
          </div>
        </section>

        <footer className="drawer-footer">
          Server processing time: {b.processing_time_ms}ms · Algorithm: {b.algorithm}
        </footer>
      </aside>
    </div>
  );
}

// ── Forecast Detail Page ─────────────────────────────────────────────────────

function ForecastDetailPage() {
  const [scenario, setScenario] = useState("heavy_rain");
  const [lead, setLead] = useState(24);
  const [result, setResult] = useState<PipelineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true); setError("");
    postJson<PipelineResponse>("/api/pipeline/run", { scenario, lead_hours: lead })
      .then(setResult).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, [scenario, lead]);

  const b = result?.blend;
  const unit = b ? VAR_UNITS[b.variable] ?? "" : "";

  return (
    <>
      <div className="toolbar">
        <div><p className="eyebrow">Canonical forecast product</p><h1>Forecast Detail</h1></div>
        <div className="controls">
          <label>Scenario
            <select value={scenario} onChange={e => setScenario(e.target.value)}>
              {Object.entries(SCENARIOS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
            <ChevronDown size={13} />
          </label>
          <label>Lead
            <select value={lead} onChange={e => setLead(Number(e.target.value))}>
              {LEADS.map(l => <option key={l} value={l}>{l}h</option>)}
            </select>
            <ChevronDown size={13} />
          </label>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      {loading && <div className="loading-block"><Spinner /></div>}
      {b && result && (
        <div className="dashboard">
          <RunHealthStrip result={result} />
          <div className="hero-band">
            <div className="hero-forecast">
              <p className="eyebrow">Point estimate</p>
              <div className="big-value">{b.blended_value.toFixed(2)}<span>{unit}</span></div>
            </div>
            <div className="hero-range">
              <p className="eyebrow">Uncertainty range</p>
              <p className="range-vals">{b.lower_bound.toFixed(2)} – {b.upper_bound.toFixed(2)} {unit}</p>
            </div>
            <div>
              <p className="eyebrow">Regime</p>
              <strong className="regime-name">{b.regime.replace(/_/g, " ")}</strong>
            </div>
            <div>
              <p className="eyebrow">Disagreement</p>
              <Badge level={b.disagreement.level} />
            </div>
          </div>
          <div className="mid-grid">
            <Panel title="Provenance" sub="Traceability fields from backend run">
              <dl className="meta-dl">
                <div><dt>Run ID</dt><dd className="mono">{b.run_id}</dd></div>
                <div><dt>Cycle time</dt><dd>{formatUtc(b.cycle_time)}</dd></div>
                <div><dt>Region</dt><dd>{b.region ?? "—"}</dd></div>
                <div><dt>Dataset version</dt><dd>{b.dataset_version ?? "—"}</dd></div>
                <div><dt>Configuration hash</dt><dd className="mono">{b.configuration_hash ?? result?.trace.configuration_hash ?? "—"}</dd></div>
                <div><dt>Algorithm</dt><dd>{b.algorithm}</dd></div>
              </dl>
            </Panel>
            <Panel title="Model weights">
              <div className="weights-list">
                {Object.entries(b.model_weights).sort((a, x) => x[1] - a[1]).map(([m, w]) => (
                  <WeightBar key={m} model={m} weight={w} unit={unit} />
                ))}
              </div>
            </Panel>
            <Panel title="Explanation drivers">
              <ol className="explanation-list">{b.explanation.map((line, i) => <li key={i}>{line}</li>)}</ol>
            </Panel>
          </div>
          <div className="scientific-note">
            Forecast guidance only. Not an official warning service. DEMO MODE · SYNTHETIC BENCHMARK.
          </div>
        </div>
      )}
    </>
  );
}

// ── Reliability Map Page ───────────────────────────────────────────────────────

function ReliabilityMapPage() {
  const [variable, setVariable] = useState("precipitation");
  const [lead, setLead] = useState(24);
  const [skills, setSkills] = useState<ModelSkillRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const chartRef = useRef<HTMLDivElement>(null);
  const [grid, setGrid] = useState<ReliabilityGrid | null>(null);
  const [selectedCell, setSelectedCell] = useState<{ value: number; latitude: number; longitude: number } | null>(null);

  useEffect(() => {
    setLoading(true); setError("");
    Promise.all([
      Promise.all(LEADS.map(h =>
        getJson<ModelSkillRow[]>(`/api/model-analysis?variable=${encodeURIComponent(variable)}&lead_hours=${h}`)
      )),
      getJson<ReliabilityGrid>(`/api/reliability/map/canonical?variable=${encodeURIComponent(variable)}&lead_hours=${lead}`),
    ])
      .then(([rows, reliabilityGrid]) => { setSkills(rows.flat()); setGrid(reliabilityGrid); setSelectedCell(null); })
      .catch(e => setError(e instanceof Error ? e.message : "Reliability load failed."))
      .finally(() => setLoading(false));
  }, [variable, lead]);

  useEffect(() => {
    if (!chartRef.current || !skills.length) return;
    const maeRows = skills.filter(row => row.metric === "mae" && row.lead_hours === lead);
    const chart = echarts.init(chartRef.current);
    chart.setOption({
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: maeRows.map(r => r.model_id.toUpperCase()) },
      yAxis: { type: "value", name: "MAE" },
      series: [{ type: "bar", data: maeRows.map(r => r.score), itemStyle: { color: "#10494d" } }],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); chart.dispose(); };
  }, [skills, lead]);

  const spatialField = useMemo<SpatialFieldResponse | null>(() => {
    if (!grid) return null;
    const values = Array.from(
      { length: grid.latitude_count },
      () => Array<number>(grid.longitude_count).fill(0),
    );
    grid.points.forEach(([longitudeIndex, latitudeIndex, value]) => {
      values[latitudeIndex][longitudeIndex] = value;
    });
    return {
      status: "AVAILABLE",
      source: "SYNTHESIS DEMO",
      model: "Historical skill reliability",
      variable: grid.variable,
      lead_hours: grid.lead_hours,
      units: "reliability index",
      latitudes: grid.latitudes,
      longitudes: grid.longitudes,
      values,
      grid_spec: {
        south: grid.latitudes[0], north: grid.latitudes[grid.latitudes.length - 1],
        west: grid.longitudes[0], east: grid.longitudes[grid.longitudes.length - 1],
        resolution: grid.resolution_degrees,
        latitude_count: grid.latitude_count, longitude_count: grid.longitude_count,
      },
      provenance: { dataset_version: grid.dataset_version, mode: grid.mode },
    };
  }, [grid]);

  const decayLeads = LEADS.map(h => ({ lead: h, skills: skills.filter(s => s.lead_hours === h && s.metric === "mae") }));

  return (
    <>
      <div className="toolbar">
        <div><p className="eyebrow">Spatial & horizon skill</p><h1>Reliability Map</h1></div>
        <div className="controls">
          <label>Variable
            <select value={variable} onChange={e => setVariable(e.target.value)}>
              <option value="precipitation">Precipitation</option>
              <option value="temperature">Temperature</option>
            </select>
            <ChevronDown size={13} />
          </label>
          <label>Lead
            <select value={lead} onChange={e => setLead(Number(e.target.value))}>
              {LEADS.map(l => <option key={l} value={l}>{l}h</option>)}
            </select>
            <ChevronDown size={13} />
          </label>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      {loading && <div className="loading-block"><Spinner /></div>}
      {!loading && skills.length > 0 && (
        <div className="dashboard">
          {grid && (
            <Panel title="Canonical India-Region Reliability Grid" sub={`141 × 141 cells · ${grid.resolution_degrees}° resolution · ${grid.latitudes[0]}–${grid.latitudes[grid.latitudes.length - 1]}°N · ${grid.longitudes[0]}–${grid.longitudes[grid.longitudes.length - 1]}°E`}>
              <SpatialFieldMap
                field={spatialField}
                title="SYNTHESIS reliability field"
                legendLabels={{ lower: "Lower reliability", upper: "Higher reliability" }}
                onCellSelect={(value, latitude, longitude) => setSelectedCell({ value, latitude, longitude })}
              />
              <p className="table-note">
                {selectedCell
                  ? `Selected cell: ${selectedCell.latitude.toFixed(2)}°N, ${selectedCell.longitude.toFixed(2)}°E — reliability index ${selectedCell.value.toFixed(3)}.`
                  : "India focus is marked within the canonical South Asia domain. Select a cell to inspect its reliability index."}
                {" "}Each cell is a backend-generated synthetic reliability index anchored to historical demo MAE for the selected variable and lead time.
              </p>
            </Panel>
          )}
          <div className="mid-grid">
            <Panel title="Relative skill by model" sub={`Metric: MAE · ${lead}h · DEMO historical skill`}>
              <div ref={chartRef} className="echart-panel" />
            </Panel>
            <Panel title="Regional reliability table" sub="Demo dataset — global region pool">
              <table className="full-table">
                <thead><tr><th>Model</th><th>Metric</th><th>Score</th><th>Cases</th><th>Region</th></tr></thead>
                <tbody>
                  {skills.filter(s => s.lead_hours === lead).map(row => (
                    <tr key={`${row.model_id}-${row.metric}`}>
                      <td><span className="model-tag">{row.model_id.toUpperCase()}</span></td>
                      <td>{row.metric.toUpperCase()}</td>
                      <td>{row.score.toFixed(3)}</td>
                      <td>{row.sample_count}</td>
                      <td>{row.region ?? "global"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
            <Panel title="Skill decay by horizon" sub="MAE at standard lead times">
              <table className="full-table">
                <thead><tr><th>Lead</th><th>Best model (lowest MAE)</th><th>MAE</th></tr></thead>
                <tbody>
                  {decayLeads.map(({ lead: h, skills: rows }) => {
                    const best = rows.sort((a, b) => a.score - b.score)[0];
                    return (
                      <tr key={h}>
                        <td>{h}h</td>
                        <td>{best ? best.model_id.toUpperCase() : "—"}</td>
                        <td>{best ? best.score.toFixed(3) : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Panel>
          </div>
          <div className="scientific-note">
            Relative skill surfaces are computed offline from the deterministic demo verification archive — not live ECMWF/GFS outputs.
          </div>
        </div>
      )}
    </>
  );
}

// ── Data Pipeline Page ────────────────────────────────────────────────────────

function PipelinePage() {
  const [result, setResult] = useState<PipelineResponse | null>(null);
  const [scenario, setScenario] = useState("heavy_rain");
  const [resilienceMode, setResilienceMode] = useState("none");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeStage, setActiveStage] = useState<number | null>(null);
  const [inputAction, setInputAction] = useState<"fetch" | "sample">("fetch");
  const stageLabels = [
    "Receive model signals", "Clean & check data", "Review past performance", "Read weather context",
    "Set model influence", "Build forecast range", "Compare with outcome",
  ];

  const run = useCallback(async (action: "fetch" | "sample" = inputAction) => {
    setLoading(true); setError("");
    setInputAction(action); setActiveStage(0);
    try {
      for (let stage = 1; stage < stageLabels.length; stage += 1) {
        await new Promise(resolve => setTimeout(resolve, 260));
        setActiveStage(stage);
      }
      const resiliencePayload = resilienceMode === "missing_gfs" ? { unavailable_sources: ["gfs"] }
        : resilienceMode === "corrupt_gfs" ? { corrupt_sources: ["gfs"] }
          : resilienceMode === "single_source" ? { corrupt_sources: ["gfs", "gefs", "ai"] }
            : resilienceMode === "all_sources" ? { unavailable_sources: ["ecmwf", "gfs", "gefs", "ai"] }
              : {};
      const data = await postJson<PipelineResponse>("/api/pipeline/run", {
        scenario, lead_hours: 24, ...resiliencePayload,
      });
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Pipeline failed.");
    } finally {
      setActiveStage(null);
      setLoading(false);
    }
  }, [inputAction, resilienceMode, scenario]);

  const trace = result?.trace;

  return (
    <>
      <div className="toolbar">
        <div><p className="eyebrow">Interactive walkthrough</p><h1>Data Pipeline</h1></div>
        <div className="controls">
          <label>Scenario
            <select value={scenario} onChange={e => setScenario(e.target.value)}>
              {Object.keys(SCENARIOS).map(k => <option key={k} value={k}>{SCENARIOS[k].label}</option>)}
            </select>
            <ChevronDown size={13} />
          </label>
          <label>Test condition
            <select value={resilienceMode} onChange={e => setResilienceMode(e.target.value)}>
              <option value="none">All sources available</option>
              <option value="missing_gfs">GFS missing</option>
              <option value="corrupt_gfs">GFS corrupt</option>
              <option value="single_source">Single-source fallback</option>
              <option value="all_sources">All sources unavailable</option>
            </select>
            <ChevronDown size={13} />
          </label>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      <div className="dashboard">
        <Panel title="Try The Pipeline" sub="Choose how to start the local demonstration">
          <div className="action-grid">
            <button className={`data-action ${inputAction === "fetch" ? "selected" : ""}`} onClick={() => void run("fetch")} disabled={loading}>
              <RefreshCw size={18} />
              <span><strong>Fetch model data</strong><small>Bring in the four ready model signals</small></span>
            </button>
            <button className={`data-action ${inputAction === "sample" ? "selected" : ""}`} onClick={() => void run("sample")} disabled={loading}>
              <Database size={18} />
              <span><strong>Load sample package</strong><small>Use the bundled local scenario data</small></span>
            </button>
          </div>
          <div className="pipeline-live" aria-live="polite" aria-label="Pipeline progress">
            {stageLabels.map((label, index) => {
              const complete = Boolean(trace) && activeStage === null;
              const current = loading && activeStage === index;
              const done = complete || (loading && activeStage !== null && index < activeStage);
              return <div key={label} className={`live-stage ${current ? "active" : done ? "done" : ""}`}>
                <span>{done ? <CheckCircle2 size={14} /> : current ? <Activity size={14} /> : index + 1}</span>
                <strong>{label}</strong>
              </div>;
            })}
          </div>
          <p className="pipeline-hint">
            {loading ? "Processing the selected scenario now…" : trace ? `Latest run: ${trace.run_id} · ${trace.status.toUpperCase()}` : "Start a run to see each stage progress in real time."}
          </p>
        </Panel>

        {loading && <div className="loading-block"><Spinner /> Processing the selected scenario…</div>}
        {trace && <>
          {result && <RunHealthStrip result={result} />}
          <div className="pipeline-grid">
            <Panel title="Source Ingestion" sub={`Run: ${trace.run_id}`}>
              <div className="source-status-list">
                {Object.entries(trace.source_availability).map(([src, avail]) => (
                  <div key={src} className={`src-status ${avail ? "ok" : "fail"}`}>
                    {avail ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                    <span className="model-tag">{src.toUpperCase()}</span>
                    <span>{avail ? "Ready" : "Unavailable"}</span>
                  </div>
                ))}
              </div>
            </Panel>
            <Panel title="What Happened" sub="Run stages completed in sequence">
              {trace.steps.map((s, i) => (
                <div key={s.name} className="pipe-step">
                  <div className="pipe-step-head">
                    <StepBadge status={s.status} />
                    <span>{i + 1}. {s.name.replace(/_/g, " ")}</span>
                    <span className="trace-ms">{s.duration_ms}ms</span>
                  </div>
                  <details className="technical-log">
                    <summary>View technical event log</summary>
                    <ul className="pipe-details">{s.details.map((d, j) => <li key={j}>{d}</li>)}</ul>
                  </details>
                </div>
              ))}
            </Panel>
            <Panel title="Run Metadata">
              <dl className="meta-dl">
                <div><dt>Run ID</dt><dd className="mono">{trace.run_id}</dd></div>
                <div><dt>Status</dt><dd><span className={`status-pill ${trace.status}`}>{trace.status.toUpperCase()}</span></dd></div>
                <div><dt>Scenario</dt><dd>{trace.scenario}</dd></div>
                <div><dt>Variable</dt><dd>{trace.variable}</dd></div>
                <div><dt>Lead hours</dt><dd>{trace.lead_hours}h</dd></div>
                <div><dt>Algorithm version</dt><dd>{trace.algorithm_version}</dd></div>
                <div><dt>Dataset version</dt><dd>{trace.dataset_version}</dd></div>
                <div><dt>Duration</dt><dd>{trace.duration_ms}ms</dd></div>
                <div><dt>Config hash</dt><dd className="mono">{shortHash(trace.configuration_hash, 16)}</dd></div>
              </dl>
            </Panel>
          </div>
          {result?.blend && (
            <div className="provenance-bar">
              <span>DEMO DATA — Synthetic benchmark sources</span>
              <span>Sources available: {Object.values(trace.source_availability).filter(Boolean).length}/4</span>
              <span>Total duration: {trace.duration_ms}ms</span>
              {trace.stale_from_run_id && <span>Last good run: {trace.stale_from_run_id}</span>}
            </div>
          )}
        </>}
      </div>
    </>
  );
}

// ── Model Analysis Page ────────────────────────────────────────────────────────

function ModelAnalysisPage() {
  const [result, setResult] = useState<PipelineResponse | null>(null);
  const [scenario, setScenario] = useState("heavy_rain");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true); setError("");
    postJson<PipelineResponse>("/api/pipeline/run", { scenario, lead_hours: 24 })
      .then(setResult).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, [scenario]);

  const reliability = result?.reliability.filter(r => r.metric === "mae") ?? [];
  const b = result?.blend;
  const unit = b ? VAR_UNITS[b.variable] ?? "" : "";

  return (
    <>
      <div className="toolbar">
        <div><p className="eyebrow">Performance Benchmarks</p><h1>Model Analysis</h1></div>
        <div className="controls">
          <label>Scenario
            <select value={scenario} onChange={e => setScenario(e.target.value)}>
              {Object.keys(SCENARIOS).map(k => <option key={k} value={k}>{SCENARIOS[k].label}</option>)}
            </select>
            <ChevronDown size={13} />
          </label>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      {loading && <div className="loading-block"><Spinner /></div>}
      {b && (
        <div className="dashboard">
          <div className="mid-grid">
            <Panel title="Historical MAE by Model" sub="DEMO DATASET — 5 verification cases per source">
              <table className="full-table">
                <thead><tr><th>Model</th><th>MAE ({unit})</th><th>Cases</th><th>Trust Weight</th></tr></thead>
                <tbody>
                  {reliability.map(r => (
                    <tr key={r.model_id}>
                      <td><span className="model-tag">{r.model_id.toUpperCase()}</span></td>
                      <td>{r.score.toFixed(3)}</td>
                      <td>{r.sample_count}</td>
                      <td>
                        <div className="inline-bar">
                          <div className="inline-fill" style={{ width: `${(b.model_weights[r.model_id] ?? 0) * 100}%` }} />
                          <span>{Math.round((b.model_weights[r.model_id] ?? 0) * 100)}%</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="table-note">Higher MAE → lower trust weight (inverse error principle)</p>
            </Panel>

            <Panel title="Adaptive Weights" sub={`Regime: ${b.regime.replace(/_/g, " ")} · ${b.disagreement.level} disagreement`}>
              <div className="weights-list">
                {Object.entries(b.model_weights).sort((a, x) => x[1] - a[1]).map(([m, w]) => (
                  <WeightBar key={m} model={m} weight={w} unit={unit} />
                ))}
              </div>
              <p className="table-note">Weights adapt to regime, disagreement level, and recent skill.</p>
            </Panel>

            <Panel title="Disagreement Analysis">
              <dl className="disagree-dl">
                <div><dt>Level</dt><dd><Badge level={b.disagreement.level} /></dd></div>
                <div><dt>Range</dt><dd>{b.disagreement.range.toFixed(2)} {unit}</dd></div>
                <div><dt>Mean</dt><dd>{b.disagreement.mean.toFixed(2)} {unit}</dd></div>
                <div><dt>Spread (σ)</dt><dd>{b.disagreement.std.toFixed(2)} {unit}</dd></div>
                <div><dt>Min</dt><dd>{b.disagreement.min_value.toFixed(2)} {unit}</dd></div>
                <div><dt>Max</dt><dd>{b.disagreement.max_value.toFixed(2)} {unit}</dd></div>
                <div><dt>Sources</dt><dd>{b.disagreement.model_count}</dd></div>
              </dl>
            </Panel>
          </div>

          <Panel title="Weight Explanation" sub="Structured traceable reasoning">
            <ol className="explanation-list">{b.explanation.map((e, i) => <li key={i}>{e}</li>)}</ol>
          </Panel>

          <div className="scientific-note">
            <ShieldCheck size={14} />
            SYNTHESIS does not claim to be more accurate than any individual model without a measured verification experiment.
            The weights above reflect historical MAE on the demo dataset (5 cases per source).
            A rigorous comparison requires a held-out chronological backtest.
          </div>
        </div>
      )}
    </>
  );
}

// ── Verification Page ─────────────────────────────────────────────────────────

function VerificationPage() {
  const [results, setResults] = useState<{ scenario: string; result: PipelineResponse }[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all(
      Object.keys(SCENARIOS).map(s =>
        postJson<PipelineResponse>("/api/pipeline/run", { scenario: s, lead_hours: 24 })
          .then(r => ({ scenario: s, result: r }))
      )
    ).then(setResults).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, []);

  return (
    <>
      <div className="toolbar">
        <div><p className="eyebrow">Forecast-vs-Observation</p><h1>Verification Results</h1></div>
      </div>
      {error && <ErrorBox message={error} />}
      {loading && <div className="loading-block"><Spinner /> Loading all scenarios…</div>}
      {results.length > 0 && (
        <div className="dashboard">
          {results.map(({ scenario, result: r }) => {
            const b = r.blend;
            const v = r.verification;
            const unit = VAR_UNITS[b.variable] ?? "";
            return (
              <Panel key={scenario} title={`${SCENARIOS[scenario].label} — ${b.variable}`} sub={`Run: ${r.run_id} · ${b.regime.replace(/_/g, " ")}`}>
                <div className="verif-grid">
                  <div className="verif-summary">
                    <div><span>SYNTHESIS Blend</span><strong>{v.forecast_value.toFixed(1)} {unit}</strong></div>
                    <div><span>Observation</span><strong>{v.observation_value.toFixed(1)} {unit}</strong></div>
                    <div><span>Error</span><strong className={Math.abs(v.error) > 5 ? "err-high" : "err-ok"}>{v.error.toFixed(1)} {unit}</strong></div>
                    <div><span>Abs. Error</span><strong>{v.absolute_error.toFixed(1)} {unit}</strong></div>
                  </div>
                  <div>
                    <table className="full-table">
                      <thead><tr><th>Model</th><th>Error ({unit})</th><th>Weight</th></tr></thead>
                      <tbody>
                        {Object.entries(v.model_errors).map(([m, err]) => (
                          <tr key={m}>
                            <td><span className="model-tag">{m.toUpperCase()}</span></td>
                            <td className={Math.abs(err) > 10 ? "err-high" : ""}>{err.toFixed(1)}</td>
                            <td>{Math.round((b.model_weights[m] ?? 0) * 100)}%</td>
                          </tr>
                        ))}
                        <tr className="total-row">
                          <td><strong>SYNTHESIS</strong></td>
                          <td><strong>{v.error.toFixed(1)}</strong></td>
                          <td>—</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </Panel>
            );
          })}
          <div className="scientific-note">
            <ShieldCheck size={14} />
            Verification is performed against deterministic synthetic observations (DEMO MODE).
            Results show the adaptive blend error relative to individual source errors for each demo scenario.
            A valid performance comparison requires a chronological backtest on real historical data.
          </div>
        </div>
      )}
    </>
  );
}

// ── Autopsy Page ──────────────────────────────────────────────────────────────

function AutopsyPage() {
  const [result, setResult] = useState<PipelineResponse | null>(null);
  const [scenario, setScenario] = useState("heavy_rain");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    postJson<PipelineResponse>("/api/pipeline/run", { scenario, lead_hours: 24 })
      .then(setResult).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, [scenario]);

  const a = result?.autopsy;
  const b = result?.blend;
  const unit = b ? VAR_UNITS[b.variable] ?? "" : "";

  return (
    <>
      <div className="toolbar">
        <div><p className="eyebrow">Post-Event Diagnostic</p><h1>Forecast Autopsy</h1></div>
        <div className="controls">
          <label>Scenario
            <select value={scenario} onChange={e => setScenario(e.target.value)}>
              {Object.keys(SCENARIOS).map(k => <option key={k} value={k}>{SCENARIOS[k].label}</option>)}
            </select>
            <ChevronDown size={13} />
          </label>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      {loading && <div className="loading-block"><Spinner /></div>}
      {a && b && (
        <div className="dashboard">
          <div className="hero-band">
            <div>
              <p className="eyebrow">SYNTHESIS Prediction</p>
              <div className="big-value">{a.forecast_value.toFixed(1)}<span>{unit}</span></div>
            </div>
            <div>
              <p className="eyebrow">Observation</p>
              <div className="big-value obs">{a.observation_value.toFixed(1)}<span>{unit}</span></div>
            </div>
            <div>
              <p className="eyebrow">Blend Error</p>
              <div className={`big-value ${Math.abs(a.blend_error) > 10 ? "err-high" : "err-ok"}`}>
                {a.blend_error.toFixed(1)}<span>{unit}</span>
              </div>
            </div>
            <div>
              <p className="eyebrow">Regime</p>
              <strong className="regime-name">{(a.regime ?? "—").replace(/_/g, " ")}</strong>
            </div>
          </div>

          <div className="mid-grid">
            <Panel title="Source-Level Analysis">
              <table className="full-table">
                <thead><tr><th>Model</th><th>Forecast</th><th>Error</th><th>Weight</th></tr></thead>
                <tbody>
                  {Object.entries(a.model_forecasts).map(([m, fc]) => {
                    const err = a.model_errors[m] ?? 0;
                    return (
                      <tr key={m}>
                        <td><span className="model-tag">{m.toUpperCase()}</span></td>
                        <td>{(fc as number).toFixed(1)} {unit}</td>
                        <td className={Math.abs(err) > 10 ? "err-high" : ""}>{err.toFixed(1)} {unit}</td>
                        <td>{Math.round((b.model_weights[m] ?? 0) * 100)}%</td>
                      </tr>
                    );
                  })}
                  <tr className="total-row">
                    <td><strong>SYNTHESIS</strong></td>
                    <td><strong>{a.forecast_value.toFixed(1)} {unit}</strong></td>
                    <td><strong>{a.blend_error.toFixed(1)} {unit}</strong></td>
                    <td>—</td>
                  </tr>
                </tbody>
              </table>
            </Panel>

            <Panel title="Diagnostic Assessment">
              <p className="assessment-text">{a.assessment}</p>
              <div className="provenance-bar" style={{ marginTop: 16 }}>
                <span>Run: {a.run_id}</span>
                <span>Valid time: {new Date(a.valid_time).toUTCString()}</span>
              </div>
            </Panel>

            <Panel title="Weights at Forecast Time">
              <div className="weights-list">
                {Object.entries(b.model_weights).sort((x, y) => y[1] - x[1]).map(([m, w]) => (
                  <WeightBar key={m} model={m} weight={w} unit={unit} value={a.model_forecasts[m] as number | undefined} />
                ))}
              </div>
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}

// ── System Status Page ─────────────────────────────────────────────────────────

function SystemPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [health, system] = await Promise.all([
        getJson<{ status: string; database?: string; version: string; demo_mode: boolean }>("/api/health"),
        getJson<SystemStatus>("/api/system/status"),
      ]);
      setStatus(system);
      setSources(system.source_adapters);
      if (health.status !== "ok") setError("The API health check reports a degraded database connection.");
    } catch (e) { setError(e instanceof Error ? e.message : "System check failed."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, []);

  const indicators = [
    { label: "API Server", key: "api", val: status?.api },
    { label: "Database", key: "db", val: status?.database },
    { label: "Pipeline", key: "pipeline", val: status?.pipeline },
    { label: "Demo Mode", key: "demo", val: status?.demo_mode ? "active" : "off" },
  ];

  return (
    <>
      <div className="toolbar">
        <div><p className="eyebrow">Infrastructure</p><h1>System Status</h1></div>
        <div className="controls">
          <button className="run-btn" onClick={load} disabled={loading}><RefreshCw size={14} /> Refresh</button>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      {loading && <div className="loading-block"><Spinner /></div>}
      {status && (
        <div className="dashboard">
          <div className="status-grid">
            {indicators.map(ind => (
              <div key={ind.key} className={`status-card ${["ok", "active", "available", "ready"].includes(String(ind.val)) ? "ok" : "warn"}`}>
                {["ok", "active", "available", "ready"].includes(String(ind.val))
                  ? <CheckCircle2 size={24} />
                  : <AlertTriangle size={24} />}
                <strong>{ind.label}</strong>
                <span>{String(ind.val ?? "—").toUpperCase()}</span>
              </div>
            ))}
            <div className="status-card ok">
              <Zap size={24} />
              <strong>Last Cycle</strong>
              <span className="mono">{status.last_cycle_run_id ?? "none yet"}</span>
            </div>
          </div>

          {sources.length > 0 && (
            <>
              <Panel title="Source Adapters" sub="DEMO MODE — Synthetic benchmark adapters">
                <div className="source-status-list">
                  {sources.map(s => (
                    <div key={s.source_id} className={`src-status ${s.status === "available" ? "ok" : "fail"}`}>
                      {s.status === "available" ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                      <span className="model-tag">{s.source_id.toUpperCase()}</span>
                      <span>{s.status.toUpperCase()}</span>
                      <span className="src-err">{s.message}</span>
                    </div>
                  ))}
                </div>
              </Panel>
              <div className="provenance-bar">
                <span>Last successful cycle: {formatUtc(status.last_successful_cycle)}</span>
                <span>Last processing time: {status.last_processing_time_ms ?? "—"}ms</span>
              </div>
            </>
          )}

          <div className="scientific-note">
            <ShieldCheck size={14} />
            SYNTHESIS Phase 1.5 operates in <strong>DEMO MODE</strong> with synthetic benchmark data.
            All forecast values are deterministic demo inputs, not live meteorological model output.
            Source adapters use the same interface as real adapters and can be replaced without changing the pipeline.
          </div>
        </div>
      )}
    </>
  );
}

// ── Root App ──────────────────────────────────────────────────────────────────

function LandingPage({ onEnterConsole, onExploreMap }: { onEnterConsole: () => void; onExploreMap: () => void }) {
  return (
    <>
      <section className="landing-hero">
        <div className="landing-content">
          <p className="landing-kicker">INDIA WEATHER INTELLIGENCE</p>
          <h1>SYNTHESIS</h1>
          <p className="landing-statement">Adaptive forecast blending for the moments when weather models disagree.</p>
          <p className="landing-copy">Bring multiple forecast signals, their recent performance, and local weather context into one clear, explainable outlook.</p>
          <div className="landing-actions">
            <button className="landing-primary" onClick={onEnterConsole}>Explore Live Console <ArrowRight size={17} /></button>
            <button className="landing-secondary" onClick={onExploreMap}>View India Reliability Map <MapPinned size={17} /></button>
          </div>
        </div>
        <div className="landing-stats" aria-label="SYNTHESIS capabilities">
          <div><strong>4</strong><span>model perspectives</span></div>
          <div><strong>141 × 141</strong><span>India-region field</span></div>
          <div><strong>7</strong><span>visible decision stages</span></div>
        </div>
      </section>
      <section className="landing-proof">
        <p className="eyebrow">BUILT FOR DECISION CONFIDENCE</p>
        <div className="landing-proof-grid">
          <div><BrainCircuit size={22} /><h2>Adaptive, not average</h2><p>Model influence changes with historical skill and the current weather situation.</p></div>
          <div><MapPinned size={22} /><h2>Spatially aware</h2><p>Explore a full India-region reliability field instead of a single black-box number.</p></div>
          <div><ShieldCheck size={22} /><h2>Explainable by design</h2><p>Every forecast retains its source health, uncertainty range, and decision trace.</p></div>
        </div>
      </section>
    </>
  );
}

function App() {
  const [page, setPage] = useState<Page | "landing">("landing");

  const PAGE_COMPONENTS: Record<Page, ReactNode> = {
    overview: <OverviewPage />,
    "forecast-detail": <ForecastDetailPage />,
    pipeline: <PipelinePage />,
    "model-analysis": <ModelAnalysisPage />,
    "reliability-map": <ReliabilityMapPage />,
    verification: <VerificationPage />,
    autopsy: <AutopsyPage />,
    system: <SystemPage />,
  };

  return (
    <div className={`app ${page === "landing" ? "landing-app" : ""}`}>
      <header className={`topbar ${page === "landing" ? "landing-topbar" : ""}`}>
        <div className="brand">
          <CloudSun size={22} />
          <span>SYNTHESIS</span>
          <small>Adaptive Forecast Blending System</small>
        </div>
        {page === "landing" ? (
          <button className="landing-nav-action" onClick={() => setPage("overview")}>Open Console <ArrowRight size={15} /></button>
        ) : <>
          <nav className="top-nav">
            {PAGES.map(p => (
              <button
                key={p}
                className={`nav-btn ${page === p ? "active" : ""}`}
                onClick={() => setPage(p)}
              >
                {PAGE_ICONS[p]} {PAGE_LABELS[p]}
              </button>
            ))}
          </nav>
          <label className="mobile-page-nav">
            <span>View</span>
            <select value={page} onChange={event => setPage(event.target.value as Page)} aria-label="Choose dashboard page">
              {PAGES.map(p => <option key={p} value={p}>{PAGE_LABELS[p]}</option>)}
            </select>
          </label>
          <div className="topbar-right">
            <ShieldCheck size={14} />
            <span>DEMO SCENARIO · LOCAL DATA</span>
          </div>
        </>}
      </header>

      <main>
        {page === "landing"
          ? <LandingPage onEnterConsole={() => setPage("overview")} onExploreMap={() => setPage("reliability-map")} />
          : PAGE_COMPONENTS[page]}
      </main>

      {page !== "landing" && <footer className="app-footer">
        <Wind size={13} />
        SYNTHESIS Phase 1.5 · Demonstration prototype · Not an official warning service
      </footer>}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
