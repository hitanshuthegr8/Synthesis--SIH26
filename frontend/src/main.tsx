import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, CloudLightning, FlaskConical, Gauge, LayoutDashboard, Map, ShieldCheck, Workflow } from "lucide-react";
import { ApiError, api, synthesis } from "./api";
import { AppContext, type PageId } from "./app/context";
import { cycleLabel } from "./lib/format";
import type { Catalog } from "./types/synthesis";
import { CommandCenter } from "./pages/CommandCenter";
import { Explorer } from "./pages/Explorer";
import { Extremes } from "./pages/Extremes";
import { Lab } from "./pages/Lab";
import { Operations } from "./pages/Operations";
import { Reliability } from "./pages/Reliability";
import { Verification } from "./pages/Verification";
import "./tokens.css";
import "./styles.css";

const PAGES: { id: PageId; label: string; icon: typeof Map; title: string; subtitle: string }[] = [
  { id: "command", label: "Command center", icon: LayoutDashboard, title: "Command center", subtitle: "Live status of the three models, blend skill and the hazard outlook." },
  { id: "explorer", label: "Blend explorer", icon: Map, title: "Blend explorer", subtitle: "The adaptive AIRAVAT field, each model, their spread, and the weights, cell by cell." },
  { id: "reliability", label: "Weight maps & skill", icon: Gauge, title: "Model weight maps & skill", subtitle: "Which model to trust for each region and lead time, and what blending gains." },
  { id: "extremes", label: "Extreme weather", icon: CloudLightning, title: "Extreme-weather guidance", subtitle: "Heavy rainfall, heat and high wind from the multi-model blend, with model agreement." },
  { id: "lab", label: "Blending lab", icon: FlaskConical, title: "Blending lab", subtitle: "Regime- and disagreement-aware blending, shown on labelled demo scenarios." },
  { id: "operations", label: "Operations", icon: Workflow, title: "Operational workflow", subtitle: "Run and schedule routine blending for a cycle." },
  { id: "verification", label: "ERA5 verification", icon: ShieldCheck, title: "Independent verification", subtitle: "Scores against ERA5 reanalysis, and the provenance of every field." },
];

function pageFromPath(): PageId {
  const id = window.location.pathname.slice(1) as PageId;
  return PAGES.some((page) => page.id === id) ? id : "command";
}

function App() {
  const [page, setPage] = useState<PageId>(pageFromPath);
  const [params, setParams] = useState(() => new URLSearchParams(window.location.search));
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [cycle, setCycle] = useState<string | undefined>(undefined);
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");

  useEffect(() => {
    void api.getHealth().then((result) => setHealth(result.status === "ok" ? "ok" : "down")).catch(() => setHealth("down"));
    void synthesis.catalog().then(setCatalog).catch((error: unknown) => setCatalogError(error instanceof ApiError ? error.message : "Catalog unavailable"));
    const onPop = () => { setPage(pageFromPath()); setParams(new URLSearchParams(window.location.search)); };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = (next: PageId, nextParams: Record<string, string> = {}) => {
    const search = new URLSearchParams(nextParams).toString();
    window.history.pushState({}, "", `/${next}${search ? `?${search}` : ""}`);
    setParams(new URLSearchParams(search));
    setPage(next);
    window.scrollTo({ top: 0 });
  };
  const current = PAGES.find((item) => item.id === page)!;
  const complete = useMemo(() => (catalog?.cycles ?? []).filter((item) => item.complete), [catalog]);

  return <AppContext.Provider value={{ catalog, catalogError, cycle, navigate, params }}>
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">A</div><div><strong>AIRAVAT</strong><small>Hybrid AI–NWP blending</small></div></div>
        <nav>{PAGES.map((item) => <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => navigate(item.id)}><item.icon size={16} />{item.label}</button>)}</nav>
        <div className="sidebar-foot">
          <span className="eyebrow">MoES · NCMRWF · SIH 2026</span>
          <p>Live GFS, IFS and AIFS open data. Demo scenarios are labelled wherever they appear.</p>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="topbar-title"><h1>{current.title}</h1><p>{current.subtitle}</p></div>
          <div className="topbar-controls">
            <label className="cycle-select"><span>Cycle</span>
              <select value={cycle ?? ""} onChange={(event) => setCycle(event.target.value || undefined)}>
                <option value="">Latest{complete[0] ? ` (${cycleLabel(complete[0].initialization)})` : ""}</option>
                {complete.map((item) => <option key={item.initialization} value={item.initialization}>{cycleLabel(item.initialization)}</option>)}
              </select>
            </label>
            <span className={`health ${health}`}><Activity size={14} />{health === "ok" ? "API online" : health === "down" ? "API offline" : "Checking"}</span>
          </div>
        </header>
        {catalogError && <div className="banner">Could not load the model catalog: {catalogError}. Is the backend running?</div>}
        {page === "command" && <CommandCenter />}
        {page === "explorer" && <Explorer key={params.toString()} />}
        {page === "reliability" && <Reliability />}
        {page === "extremes" && <Extremes />}
        {page === "lab" && <Lab />}
        {page === "operations" && <Operations />}
        {page === "verification" && <Verification />}
      </main>
    </div>
  </AppContext.Provider>;
}

export default App;

createRoot(document.getElementById("root")!).render(<App />);
