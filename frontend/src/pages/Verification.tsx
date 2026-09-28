import { useState } from "react";
import { KeyRound } from "lucide-react";
import { api } from "../api";
import { useApp } from "../app/context";
import { SpatialFieldMap } from "../components/SpatialFieldMap";
import { Card, KeyValue, Loading, Notice, Segmented, Stat } from "../components/ui";
import { cycleLabel, number } from "../lib/format";
import { useAsync } from "../lib/useAsync";

export function Verification() {
  const { cycle, catalog } = useApp();
  const [source, setSource] = useState<"GFS" | "ECMWF">("GFS");
  const [lead, setLead] = useState(24);
  const initialization = cycle ?? catalog?.cycles.find((item) => item.complete)?.initialization;
  const forecast = useAsync(initialization ? () => api.getSpatialForecast(source, source === "GFS" ? "GFS" : "IFS", "temperature", lead, initialization) : null, [source, lead, initialization]);
  const result = useAsync(initialization ? () => api.verifySpatialForecast(source, source === "GFS" ? "GFS" : "IFS", "temperature", lead, initialization) : null, [source, lead, initialization]);
  const verification = result.data;
  const errorField = verification?.status === "AVAILABLE" && forecast.data
    ? { ...forecast.data, values: verification.absolute_error_field ?? null, source: "Absolute error" }
    : null;

  return <div className="page verification">
    <div className="page-toolbar">
      <Segmented label="Model" value={source} onChange={setSource} options={[{ value: "GFS", label: "NOAA GFS" }, { value: "ECMWF", label: "ECMWF IFS" }]} />
      <Segmented label="Lead" value={lead} onChange={setLead} options={[24, 48, 72].map((value) => ({ value, label: `+${value} h` }))} />
      <span className="toolbar-note">Independent verification against ERA5 reanalysis for {cycleLabel(initialization)}; 2 m temperature.</span>
    </div>
    {!catalog?.era5_enabled && <Notice tone="warn" title="ERA5 is not configured" action={<p className="fine"><KeyRound size={12} /> Add <code>ERA5_ENABLED=true</code> and <code>ERA5_CDS_KEY=…</code> to <code>backend/.env</code> (free key from the Copernicus Climate Data Store), then restart the backend.</p>}>
      The weight maps are scored against model analyses, which favour whichever model produced them. ERA5 is the independent reference that can show whether the blend beats every single model. It is published about five days late, so it scores older cycles that the operational run has archived.
    </Notice>}
    {result.status === "loading" && <Card><Loading label="Requesting ERA5 truth…" /></Card>}
    {verification?.status === "UNAVAILABLE" && catalog?.era5_enabled && <Notice tone="warn" title="Verification unavailable">{verification.reason}</Notice>}
    {verification?.status === "AVAILABLE" && verification.metrics && <>
      <section className="stat-row">
        <Stat label="MAE" value={number(verification.metrics.mae, 2)} unit="°C" />
        <Stat label="RMSE" value={number(verification.metrics.rmse, 2)} unit="°C" />
        <Stat label="Bias" value={number(verification.metrics.bias, 2)} unit="°C" />
        <Stat label="Valid cells" value={verification.metrics.valid_cell_count.toLocaleString()} unit={`/ ${verification.metrics.total_cell_count.toLocaleString()}`} />
      </section>
      <div className="two-col">
        <SpatialFieldMap field={forecast.data} title={`${source} forecast`} />
        <SpatialFieldMap field={errorField} title="Absolute error vs ERA5" palette="error" scale="linear" />
      </div>
    </>}
    <Card eyebrow="PROVENANCE" title="Forecast source record">
      {forecast.status === "loading" ? <Loading label="Loading forecast metadata…" /> : forecast.data?.status === "AVAILABLE"
        ? <KeyValue items={Object.entries(forecast.data.provenance ?? {}).filter(([, value]) => typeof value === "string" || typeof value === "number").slice(0, 16).map(([key, value]) => [key.replace(/_/g, " "), String(value)])} />
        : <p className="muted-text">{forecast.data?.reason ?? forecast.error ?? "No forecast loaded."}</p>}
    </Card>
  </div>;
}
