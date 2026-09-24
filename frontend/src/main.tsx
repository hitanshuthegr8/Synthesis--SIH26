import { useEffect, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { AlertCircle, ChevronDown, CloudSun, RefreshCw, ShieldCheck, Wind } from "lucide-react";
import "./styles.css";

type Forecast = { model_id: string; value: number; unit: string };
type Blend = { blended_value: number; lower_bound: number; upper_bound: number; model_weights: Record<string, number>; disagreement: { level: string; range: number; std: number; model_count: number }; regime: string; regime_confidence: number; explanation: string[] };
type Reliability = { model_id: string; mae: number; sample_count: number; reliability: number; sufficient_samples: boolean };
type Verification = { forecast_value: number; observation_value: number; error: number; absolute_error: number; model_errors: Record<string, number> };

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const labels: Record<string, string> = { temperature: "Temperature", precipitation: "Precipitation", wind_speed: "Wind speed" };
const units: Record<string, string> = { temperature: "C", precipitation: "mm", wind_speed: "m/s" };
const scenarios: Record<string, { label: string; variable: string }> = { normal: { label: "Normal", variable: "temperature" }, heavy_rain: { label: "Heavy rain", variable: "precipitation" }, model_conflict: { label: "Model conflict", variable: "precipitation" } };

function App() {
  const [variable, setVariable] = useState("temperature");
  const [scenario, setScenario] = useState("normal");
  const [lead, setLead] = useState(24);
  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [blend, setBlend] = useState<Blend | null>(null);
  const [reliability, setReliability] = useState<Reliability[]>([]);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true); setError("");
    try {
      const scenarioParam = scenario === "custom" ? "" : `&scenario=${scenario}`;
      const query = `variable=${variable}&lead_hours=${lead}${scenarioParam}`;
      const [forecastResponse, blendResponse, reliabilityResponse, verificationResponse] = await Promise.all([
        fetch(`${baseUrl}/api/forecasts?${query}`), fetch(`${baseUrl}/api/blend`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ variable, lead_hours: lead, scenario: scenario === "custom" ? null : scenario }) }),
        fetch(`${baseUrl}/api/reliability/model?${query}`), fetch(`${baseUrl}/api/verification?${query}`)
      ]);
      if (![forecastResponse, blendResponse, reliabilityResponse, verificationResponse].every((item) => item.ok)) throw new Error("The forecast service is unavailable.");
      setForecasts(await forecastResponse.json()); setBlend(await blendResponse.json()); setReliability(await reliabilityResponse.json()); setVerification(await verificationResponse.json());
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load forecast data."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [variable, lead, scenario]);
  const unit = units[variable];

  return <main>
    <header className="topbar"><div className="brand"><CloudSun size={26}/><span>SYNTHESIS</span><small>Hybrid forecast console</small></div><div className="status"><ShieldCheck size={16}/> DEMO DATA</div></header>
    <section className="toolbar"><div><p className="eyebrow">Forecast workspace</p><h1>{labels[variable]} outlook</h1></div><div className="controls"><label>Scenario<select value={scenario} onChange={(e) => { const next = e.target.value; if (next !== "custom") { setVariable(scenarios[next].variable); } setScenario(next); }}><option value="normal">Normal</option><option value="heavy_rain">Heavy rain</option><option value="model_conflict">Model conflict</option><option value="custom">Custom demo</option></select><ChevronDown size={15}/></label><label>Variable<select value={variable} onChange={(e) => { setVariable(e.target.value); setScenario("custom"); }}><option value="temperature">Temperature</option><option value="precipitation">Precipitation</option><option value="wind_speed">Wind speed</option></select><ChevronDown size={15}/></label><label>Lead time<select value={lead} onChange={(e) => setLead(Number(e.target.value))}><option value={24}>24 hours</option><option value={48}>48 hours</option><option value={72}>72 hours</option></select><ChevronDown size={15}/></label><button onClick={() => void load()} title="Refresh forecast data" aria-label="Refresh forecast data"><RefreshCw size={18}/></button></div></section>
    {error && <div className="error"><AlertCircle size={18}/>{error}</div>}
    {loading ? <div className="loading">Updating forecast workspace...</div> : blend && <div className="dashboard">
      <section className="forecast-band"><div><p className="eyebrow">Weighted forecast</p><div className="forecast-value">{blend.blended_value.toFixed(1)} <span>{unit}</span></div><p>{lead}-hour outlook · {blend.regime.replace(/_/g, " ")}</p></div><div className="range"><p className="eyebrow">Forecast uncertainty range</p><strong>{blend.lower_bound.toFixed(1)} – {blend.upper_bound.toFixed(1)} {unit}</strong><div className="range-track"><i style={{ left: "22%", width: "56%" }}/><b style={{ left: "50%" }}/></div><small>Not a calibrated confidence interval</small></div><div className="regime"><p className="eyebrow">Regime signal</p><strong>{blend.regime.replace(/_/g, " ")}</strong><span>{Math.round(blend.regime_confidence * 100)}% rule-based confidence</span></div></section>
      <section className="grid primary"><Panel title="Source forecasts"><div className="forecast-list">{forecasts.map((item) => <div key={item.model_id}><span>{item.model_id.toUpperCase()}</span><strong>{item.value.toFixed(1)} {unit}</strong></div>)}</div></Panel><Panel title="Model weights"><div className="weights">{Object.entries(blend.model_weights).sort((a,b)=>b[1]-a[1]).map(([model, weight]) => <div key={model}><div><span>{model.toUpperCase()}</span><strong>{Math.round(weight * 100)}%</strong></div><i><b style={{ width: `${weight * 100}%` }}/></i></div>)}</div></Panel><Panel title="Model disagreement"><div className="disagreement"><div className={`level ${blend.disagreement.level.toLowerCase()}`}>{blend.disagreement.level}</div><dl><div><dt>Range</dt><dd>{blend.disagreement.range.toFixed(1)} {unit}</dd></div><div><dt>Spread</dt><dd>{blend.disagreement.std.toFixed(1)} {unit}</dd></div><div><dt>Sources</dt><dd>{blend.disagreement.model_count}</dd></div></dl></div></Panel></section>
      <section className="grid secondary"><Panel title="Historical reliability"><table><thead><tr><th>Model</th><th>MAE</th><th>Samples</th><th>Trust</th></tr></thead><tbody>{reliability.map((item) => <tr key={item.model_id}><td>{item.model_id.toUpperCase()}</td><td>{item.mae.toFixed(2)} {unit}</td><td>{item.sample_count}</td><td>{Math.round(item.reliability * 100)}%</td></tr>)}</tbody></table></Panel><Panel title="Why this blend"><ol className="explanations">{blend.explanation.map((item, index) => <li key={index}>{item}</li>)}</ol></Panel><Panel title="Forecast autopsy"><div className="autopsy"><div><span>Prediction</span><strong>{verification?.forecast_value.toFixed(1)} {unit}</strong></div><div><span>Observation</span><strong>{verification?.observation_value.toFixed(1)} {unit}</strong></div><div><span>Absolute error</span><strong>{verification?.absolute_error.toFixed(1)} {unit}</strong></div></div></Panel></section>
    </div>}
    <footer><Wind size={15}/> Deterministic demo inputs · scores display their sample counts</footer>
  </main>;
}
function Panel({ title, children }: { title: string; children: ReactNode }) { return <article className="panel"><h2>{title}</h2>{children}</article>; }
createRoot(document.getElementById("root")!).render(<App />);
