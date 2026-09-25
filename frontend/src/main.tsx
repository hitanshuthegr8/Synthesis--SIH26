import { useEffect, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { AlertCircle, CheckCircle2, ChevronDown, Database, Info, RefreshCw, ShieldCheck } from "lucide-react";
import { ApiError, api } from "./api";
import type { GridSpec, SpatialFieldResponse, SpatialVerificationResponse } from "./types/api";
import { SpatialFieldMap } from "./components/SpatialFieldMap";
import "./styles.css";
import "./tokens.css";

type Page = "overview" | "forecast" | "verification" | "provenance";
type Source = "GFS" | "ECMWF" | "SYNTHESIS";
const init = "2026-09-25T00:00:00Z";
const pages: { id: Page; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "forecast", label: "Forecast explorer" },
  { id: "verification", label: "Verification" },
  { id: "provenance", label: "Data & provenance" },
];

function App() {
  const [page, setPage] = useState<Page>(() => (pages.some((item) => `/${item.id}` === window.location.pathname) ? window.location.pathname.slice(1) as Page : "overview"));
  const [source, setSource] = useState<Source>("SYNTHESIS");
  const [lead, setLead] = useState(24);
  const [field, setField] = useState<SpatialFieldResponse | null>(null);
  const [verification, setVerification] = useState<SpatialVerificationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [selectedCell, setSelectedCell] = useState<{ value: number; latitude: number; longitude: number } | null>(null);
  const [health, setHealth] = useState("Checking system");

  const load = async () => {
    setLoading(true);
    setNotice("");
    setSelectedCell(null);
    try {
      const selectedField = source === "SYNTHESIS"
        ? await api.getSpatialBlend("temperature", lead, init)
        : await api.getSpatialForecast(source, source === "GFS" ? "GFS" : "IFS", "temperature", lead, init);
      setField(selectedField);
      if (page === "verification") {
        if (source === "SYNTHESIS") {
          setVerification({ status: "UNAVAILABLE", reason: "Verification unavailable for SYNTHESIS: the ERA5 reference dataset is currently unavailable. No verification score was generated." });
        } else {
          const result = await api.verifySpatialForecast(source, source === "ECMWF" ? "IFS" : "GFS", "temperature", lead, init);
          setVerification(result);
        }
      }
      if (selectedField.status === "UNAVAILABLE") setNotice(selectedField.reason ?? "Forecast unavailable for this request.");
    } catch (error) {
      setNotice(error instanceof ApiError ? error.message : "The forecast service could not be reached.");
      setField(null);
      setVerification(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void api.getHealth().then((result) => setHealth(result.status === "ok" ? "Operational" : "Degraded")).catch(() => setHealth("Unavailable")); }, []);
  useEffect(() => { void load(); }, [source, lead, page]);
  const navigate = (next: Page) => { window.history.pushState({}, "", `/${next}`); setPage(next); };
  const grid = field?.grid_spec;

  return <main>
    <header className="topbar"><div className="brand"><div className="brand-mark">S</div><div><strong>SYNTHESIS</strong><small>Spatial forecast intelligence</small></div></div><nav>{pages.map((item) => <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => navigate(item.id)}>{item.label}</button>)}</nav><div className="system-status"><span className="status-dot" />{health}</div></header>
    <section className="page-heading"><div><span className="eyebrow">COMMAND CENTER · INDIA DOMAIN</span><h1>{page === "overview" ? "Forecast, compare, and verify weather predictions." : pages.find((item) => item.id === page)?.label}</h1><p>{page === "overview" ? "SYNTHESIS turns supported spatial forecasts into an evidence-led view of what was predicted and where it differs." : "Every result is tied to a real provider, a fixed grid, and explicit provenance."}</p></div><div className="run-meta"><span>00Z initialization</span><span>Lead {lead}h</span></div></section>
    {notice && <div className="notice"><AlertCircle size={17} /><div><strong>{notice.toLowerCase().includes("unavailable") ? "Verification or forecast unavailable" : "Request could not be completed"}</strong><span>{notice}</span></div></div>}
    {page === "overview" && <Overview field={field} health={health} grid={grid} loading={loading} onNavigate={navigate} />}
    {page === "forecast" && <ForecastExplorer source={source} setSource={setSource} lead={lead} setLead={setLead} loading={loading} field={field} selectedCell={selectedCell} setSelectedCell={setSelectedCell} refresh={load} />}
    {page === "verification" && <VerificationView field={field} verification={verification} loading={loading} onNavigate={navigate} source={source} />}
    {page === "provenance" && <Provenance field={field} verification={verification} grid={grid} source={source} />}
    <footer><ShieldCheck size={15} /> No synthetic truth in production · unavailable data remains unavailable</footer>
  </main>;
}

function Overview({ field, health, grid, loading, onNavigate }: { field: SpatialFieldResponse | null; health: string; grid?: GridSpec; loading: boolean; onNavigate: (page: Page) => void }) {
  return <div className="content"><section className="hero-grid"><article className="hero-card"><span className="eyebrow">SYNTHESIS / TRANSPARENT BY DESIGN</span><h2>One view from forecast to evidence.</h2><p>Combine supported spatial forecasts, compare them against ERA5 when available, and see exactly where the field carries error.</p><div className="hero-actions"><button className="primary-button" onClick={() => onNavigate("forecast")}>Open forecast explorer <span>→</span></button><button className="text-button" onClick={() => onNavigate("verification")}>See verification path</button></div></article><article className="status-card"><div className="card-title"><span>DATA STATUS</span><Database size={18} /></div><div className="status-row"><span>Forecast field</span><strong className={field?.status === "AVAILABLE" ? "good" : "muted"}>{loading ? "Loading" : field?.status === "AVAILABLE" ? "Available" : "Unavailable"}</strong></div><div className="status-row"><span>Reference truth</span><strong className="muted">ERA5 · on demand</strong></div><div className="status-row"><span>Verification</span><strong className="muted">Requires ERA5 access</strong></div></article></section><section className="section-grid"><InfoCard label="CURRENT SOURCE" value={field?.source ?? "SYNTHESIS"} detail={field?.model ?? "Equal-weight blend path"} /><InfoCard label="SYSTEM" value={health} detail="API health endpoint" /><InfoCard label="TARGET GRID" value={grid ? `${grid.latitude_count} × ${grid.longitude_count}` : "141 × 141"} detail="5–40°N · 65–100°E · 0.25°" /></section><section className="overview-flow"><div><span className="eyebrow">THE PRODUCT JOURNEY</span><h2>Forecast → truth → verification</h2></div><div className="flow"><FlowStep number="01" title="Forecast" text="GFS, ECMWF IFS, or SYNTHESIS on the fixed India grid." /><span className="flow-arrow">→</span><FlowStep number="02" title="ERA5 truth" text="Reference data is requested only when configured and available." /><span className="flow-arrow">→</span><FlowStep number="03" title="Verification" text="MAE, RMSE, bias, and absolute error field." /></div></section></div>;
}

function ForecastExplorer({ source, setSource, lead, setLead, loading, field, selectedCell, setSelectedCell, refresh }: { source: Source; setSource: (value: Source) => void; lead: number; setLead: (value: number) => void; loading: boolean; field: SpatialFieldResponse | null; selectedCell: { value: number; latitude: number; longitude: number } | null; setSelectedCell: (value: { value: number; latitude: number; longitude: number } | null) => void; refresh: () => void }) {
  return <div className="content"><section className="explorer-layout"><aside className="control-panel"><span className="eyebrow">REQUEST</span><h2>Forecast explorer</h2><Control label="Source / model"><select value={source} onChange={(event) => setSource(event.target.value as Source)}><option value="SYNTHESIS">SYNTHESIS blend</option><option value="GFS">NOAA GFS</option><option value="ECMWF">ECMWF IFS</option></select><ChevronDown size={15} /></Control><Control label="Variable"><div className="readonly-control">2m temperature <span>°C</span></div></Control><Control label="Initialization"><div className="readonly-control">25 Sep 2026 · 00Z</div></Control><Control label="Lead time"><select value={lead} onChange={(event) => setLead(Number(event.target.value))}>{[24, 48, 72, 120, 168].map((value) => <option key={value} value={value}>{value} hours</option>)}</select><ChevronDown size={15} /></Control><button className="secondary-button" onClick={refresh} disabled={loading}><RefreshCw size={15} /> {loading ? "Loading field..." : "Refresh field"}</button><div className="control-note"><Info size={15} /><span>Strict 141 × 141 grid. No interpolation or fallback data.</span></div></aside><section className="map-panel"><div className="panel-header"><div><span className="eyebrow">FORECAST FIELD</span><h2>{source === "SYNTHESIS" ? "SYNTHESIS weighted mean" : `${source} spatial temperature`}</h2></div><StatusBadge available={field?.status === "AVAILABLE"} label={loading ? "LOADING" : undefined} /></div>{field?.status === "AVAILABLE" && <ForecastSummary field={field} source={source} />}{loading ? <MapSkeleton /> : <SpatialFieldMap field={field} title={source === "SYNTHESIS" ? "SYNTHESIS weighted mean" : `${source} forecast`} onCellSelect={(value, latitude, longitude) => setSelectedCell({ value, latitude, longitude })} />}</section><aside className="inspect-panel"><span className="eyebrow">CELL INSPECTOR</span><h2>{selectedCell ? `${selectedCell.value.toFixed(1)} °C` : "Select a cell"}</h2>{selectedCell ? <p><strong>{selectedCell.latitude.toFixed(2)}°N</strong> · <strong>{selectedCell.longitude.toFixed(2)}°E</strong><br />Forecast value at nearest 0.25° cell</p> : <p>Click anywhere on the grid to inspect the nearest cell.</p>}<div className="mini-detail"><span>Field status</span><strong>{loading ? "Loading" : field?.status ?? "Waiting"}</strong></div><div className="mini-detail"><span>Units</span><strong>{field?.units ?? "—"}</strong></div><div className="mini-detail"><span>Domain</span><strong>India · 0.25°</strong></div></aside></section></div>;
}

function ForecastSummary({ field, source }: { field: SpatialFieldResponse; source: Source }) {
  const sourceWeights = field.provenance?.source_weights;
  const weights = sourceWeights && typeof sourceWeights === "object"
    ? Object.entries(sourceWeights as Record<string, unknown>).map(([name, weight]) => `${name} ${Number(weight) * 100}%`).join(" · ")
    : "Weights not provided";
  const method = typeof field.provenance?.blend_method === "string" ? field.provenance.blend_method : "Weighted mean";
  return <div className="forecast-summary"><strong>{source}</strong><span>{source === "SYNTHESIS" ? method : field.model ?? "Model not provided"}</span><span>{source === "SYNTHESIS" ? weights : "141 × 141 · 0.25°"}</span></div>;
}

function VerificationView({ field, verification, loading, onNavigate, source }: { field: SpatialFieldResponse | null; verification: SpatialVerificationResponse | null; loading: boolean; onNavigate: (page: Page) => void; source: Source }) {
  const errorField = verification?.status === "AVAILABLE" ? { ...field, status: "AVAILABLE" as const, values: verification.absolute_error_field ?? null, units: field?.units ?? "°C", source: "Absolute error" } : null;
  return <div className="content"><section className="verification-intro"><div><span className="eyebrow">MEASUREMENT, NOT CONFIDENCE</span><h2>Where was the forecast wrong?</h2><p>Verification is only produced when a real ERA5 reference field is available for the same valid UTC time and grid.</p></div><StatusBadge available={verification?.status === "AVAILABLE"} label={loading ? "LOADING" : undefined} /></section><div className="verification-flow"><span>{source} FORECAST</span><i>↓</i><span>REFERENCE / ERA5</span><i>↓</i><strong>VERIFICATION</strong></div>{loading ? <VerificationSkeleton /> : verification?.status === "AVAILABLE" && verification.metrics ? <><section className="metric-grid"><Metric label="MAE · mean absolute error" value={verification.metrics.mae.toFixed(2)} unit="°C" /><Metric label="RMSE · larger errors emphasized" value={verification.metrics.rmse.toFixed(2)} unit="°C" /><Metric label="BIAS · systematic direction" value={verification.metrics.bias.toFixed(2)} unit="°C" /><Metric label="VALID CELLS" value={verification.metrics.valid_cell_count.toLocaleString()} unit={`/ ${verification.metrics.total_cell_count.toLocaleString()}`} /></section><section className="verification-maps"><div className="map-card"><SpatialFieldMap field={field} title="Forecast field" /></div><div className="map-card error-map-card"><SpatialFieldMap field={errorField} title="Absolute error field" /></div></section><ProvenanceSummary provenance={verification.provenance ?? {}} field={field} source={source} /></> : <UnavailableCard title={`${source} verification unavailable`} text={verification?.reason ?? "The reference dataset required for verification is currently unavailable. No verification score was generated."} action={() => onNavigate("provenance")} />}</div>;
}

function Provenance({ field, verification, grid, source }: { field: SpatialFieldResponse | null; verification: SpatialVerificationResponse | null; grid?: GridSpec; source: Source }) {
  const provenance = verification?.provenance ?? field?.provenance ?? {};
  return <div className="content"><section className="provenance-head"><span className="eyebrow">TRACEABLE OUTPUT</span><h2>Data & provenance</h2><p>Every field is accompanied by its source, grid, timing, and normalization details.</p></section><ProvenanceSummary provenance={provenance} field={field} grid={grid} source={source} /><section className="trust-note"><CheckCircle2 size={19} /><div><strong>Provenance is not confidence.</strong><p>These records explain where the data came from and how it was compared. They do not claim universal forecast skill.</p></div></section></div>;
}

function ProvenanceSummary({ provenance, field, grid, source }: { provenance: Record<string, unknown>; field: SpatialFieldResponse | null; grid?: GridSpec; source: Source }) {
  const sourceModels: string | undefined = Array.isArray(provenance.source_models) ? provenance.source_models.map((item) => {
    if (!item || typeof item !== "object") return "Not provided";
    const value = item as Record<string, unknown>;
    return `${String(value.source ?? "Not provided")} (${String(value.model ?? "Not provided")})`;
  }).join(" · ") : undefined;
  const weights = provenance.source_weights && typeof provenance.source_weights === "object"
    ? Object.entries(provenance.source_weights as Record<string, unknown>).map(([name, weight]) => `${name} ${Number(weight) * 100}%`).join(" · ")
    : undefined;
  const value = (key: string, fallback?: unknown): string | number | undefined => {
    const result = provenance[key] ?? fallback;
    return typeof result === "string" || typeof result === "number" ? result : undefined;
  };
  const entries: [string, string | number | undefined][] = [
    ["Forecast source", source === "SYNTHESIS" ? "SYNTHESIS" : source === "GFS" ? "GFS" : "ECMWF"],
    ["Forecast model", value("model", field?.model)],
    ["Initialization", value("initialization", field?.initialization)],
    ["Lead hours", value("lead_hours", field?.lead_hours)],
    ["Valid UTC time", value("valid_time")],
    ["Variable", value("variable", field?.variable)],
    ["Forecast units", value("units", field?.units)],
    ["Truth provider", value("truth_source")],
    ["Truth dataset", (provenance.truth_provenance as Record<string, unknown> | undefined)?.dataset as string | undefined],
    ["Truth units", value("truth_units")],
    ["Grid", grid ? `${grid.latitude_count} × ${grid.longitude_count} · ${grid.resolution}°` : undefined],
    ["Underlying sources", sourceModels],
    ["Weights", weights],
    ["Blend method", value("blend_method")],
    ["Weight policy", value("weight_policy")],
    ["Metrics", Array.isArray(provenance.metrics) ? provenance.metrics.join(", ") : undefined],
  ];
  return <section className="provenance-panel"><div className="panel-header"><div><span className="eyebrow">VERIFICATION DETAILS</span><h2>Why can I trust this result?</h2></div><span className="confidence-note">NOT A CONFIDENCE SCORE</span></div><div className="provenance-grid">{entries.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value ? String(value) : "—"}</strong></div>)}</div></section>;
}

function Control({ label, children }: { label: string; children: ReactNode }) { return <label className="control"><span>{label}</span><div>{children}</div></label>; }
function MapSkeleton() { return <div className="map-skeleton" aria-label="Loading spatial field"><div className="skeleton-grid" /><span>Loading verified spatial field…</span></div>; }
function VerificationSkeleton() { return <div className="verification-skeleton"><div /><div /><div /></div>; }
function InfoCard({ label, value, detail }: { label: string; value: string; detail: string }) { return <article className="info-card"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>; }
function FlowStep({ number, title, text }: { number: string; title: string; text: string }) { return <div className="flow-step"><span>{number}</span><strong>{title}</strong><p>{text}</p></div>; }
function Metric({ label, value, unit }: { label: string; value: string; unit: string }) { return <article className="metric-card"><span>{label}</span><strong>{value}<small>{unit}</small></strong></article>; }
function StatusBadge({ available, label }: { available: boolean; label?: string }) { return <span className={`status-badge ${available ? "available" : "unavailable"}`}><span />{label ?? (available ? "AVAILABLE" : "UNAVAILABLE")}</span>; }
function UnavailableCard({ title, text, action }: { title: string; text: string; action: () => void }) { return <section className="unavailable-card"><AlertCircle size={22} /><div><h2>{title}</h2><p>{text}</p><button className="secondary-button" onClick={action}>View data requirements</button></div></section>; }

export default App;

createRoot(document.getElementById("root")!).render(<App />);
