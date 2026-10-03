import { useState } from "react";
import { CloudRainWind, Thermometer, Wind } from "lucide-react";
import { synthesis } from "../api";
import { useApp } from "../app/context";
import { SpatialFieldMap } from "../components/SpatialFieldMap";
import type { FieldPalette } from "../components/fieldPalette";
import { Card, LevelChip, Loading, Notice, Segmented, SourceTag } from "../components/ui";
import { SOURCE_ORDER, area, coordinate, istTime, number, watchSignal } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import type { Hazard, SourceId } from "../types/synthesis";

const HAZARD_META: Record<Hazard["hazard"], { icon: typeof Wind; palette: FieldPalette; scale: "linear" | "quantile"; basis: string }> = {
  heavy_rain: { icon: CloudRainWind, palette: "rain", scale: "linear", basis: "24 h rainfall, IMD categories" },
  heat: { icon: Thermometer, palette: "thermal", scale: "quantile", basis: "Afternoon maximum (6 h ending 12 UTC), absolute thresholds" },
  high_wind: { icon: Wind, palette: "wind", scale: "linear", basis: "10 m wind at 12 UTC, Beaufort 6/7/8" },
};

export function Extremes() {
  const { cycle } = useApp();
  const [day, setDay] = useState(1);
  const [selected, setSelected] = useState<Hazard["hazard"]>("heavy_rain");
  const guidance = useAsync(() => synthesis.extremes(day, cycle), [day, cycle]);
  const field = useAsync(() => synthesis.extremeField(selected, day, cycle), [selected, day, cycle]);
  const initialization = guidance.data?.initialization ?? cycle;
  const dayLabel = (value: number) => {
    if (!initialization) return value === 0 ? "Day 0" : `Day +${value}`;
    const date = new Date(new Date(initialization).getTime() + value * 86_400_000);
    return `${value === 0 ? "Today" : `D+${value}`} · ${date.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" })}`;
  };
  const hazards = guidance.data?.hazards ?? [];
  const active = hazards.find((hazard) => hazard.hazard === selected);

  return <div className="page extremes">
    <div className="page-toolbar">
      <Segmented label="Forecast day" value={day} onChange={setDay} options={[0, 1, 2, 3, 4].map((value) => ({ value, label: dayLabel(value) }))} />
      <span className="toolbar-note">Guidance from the multi-model mean of GFS, IFS and AIFS; agreement shows how many models independently cross the first threshold.</span>
    </div>
    {guidance.status === "loading" && !guidance.data && <Card><Loading label="Scanning all models for hazards…" /></Card>}
    {guidance.status === "error" && <Notice tone="error" title="Extreme-weather request failed" action={<button className="btn ghost" onClick={guidance.reload}>Retry</button>}>{guidance.error}</Notice>}
    {guidance.data?.status === "UNAVAILABLE" && <Notice tone="warn" title="Guidance unavailable">{guidance.data.reason}</Notice>}

    {hazards.length > 0 && <section className="hazard-grid">
      {hazards.map((hazard) => <HazardCard key={hazard.hazard} hazard={hazard} selected={hazard.hazard === selected} onSelect={() => setSelected(hazard.hazard)} />)}
    </section>}

    <div className="two-col wide-left">
      <div className="map-stage">
        {field.status === "loading" && !field.data ? <Card><Loading label="Loading hazard field…" /></Card>
          : <SpatialFieldMap field={field.data} title={`${active?.label ?? "Hazard"} · ${HAZARD_META[selected].basis}`} palette={HAZARD_META[selected].palette} scale={HAZARD_META[selected].scale} />}
      </div>
      {active?.status === "AVAILABLE" && <Card eyebrow="HOTSPOTS" title={active.label}>
        <p className="muted-text">{active.hazard === "heavy_rain" ? "24 h ending" : "Valid"} {istTime(active.valid_time)} · thresholds {active.levels?.map((level) => `${level.label} ≥ ${level.threshold}`).join(", ")} {active.units}</p>
        {active.hotspots?.length ? <ol className="hotspots">{active.hotspots.map((spot) => <li key={`${spot.latitude}-${spot.longitude}`}><strong>{number(spot.value)} {active.units}</strong><span>{coordinate(spot.latitude, spot.longitude)}</span></li>)}</ol>
          : <p className="muted-text">No cell in India reaches the first threshold on the blended field.</p>}
        <p className="fine">{active.blend}{Object.keys(active.missing_sources ?? {}).length ? ` · not available: ${Object.entries(active.missing_sources ?? {}).map(([source, reason]) => `${source} (${reason})`).join("; ")}` : ""}</p>
      </Card>}
    </div>
  </div>;
}

function HazardCard({ hazard, selected, onSelect }: { hazard: Hazard; selected: boolean; onSelect: () => void }) {
  const meta = HAZARD_META[hazard.hazard];
  const Icon = meta.icon;
  if (hazard.status !== "AVAILABLE") {
    return <button className={`hazard-card ${selected ? "selected" : ""}`} onClick={onSelect}>
      <header><Icon size={18} /><strong>{hazard.label}</strong></header>
      <p className="muted-text">Unavailable: {hazard.reason}</p>
    </button>;
  }
  const levels = hazard.levels ?? [];
  const agreement = hazard.agreement!;
  const total = agreement.all_models_km2 + agreement.some_models_km2;
  const watch = hazard.highest_level ? null : watchSignal(agreement);
  return <button className={`hazard-card ${selected ? "selected" : ""}`} onClick={onSelect}>
    <header><Icon size={18} /><strong>{hazard.label}</strong><LevelChip level={hazard.highest_level} levels={levels.map((level) => level.label)} watch={watch} /></header>
    {watch && <p className="watch-note">{watch} at ≥ {agreement.threshold} {hazard.units}; the blend stays below it. Treat as a low-confidence signal to monitor.</p>}
    <div className="hazard-peak">
      <span>Peak {number(hazard.peak?.value)} {hazard.units}</span>
      <em>{hazard.peak ? coordinate(hazard.peak.latitude, hazard.peak.longitude) : ""}</em>
    </div>
    <div className="peak-models">{SOURCE_ORDER.filter((source) => hazard.peak?.by_source[source] !== undefined).map((source: SourceId) => <span key={source}><SourceTag source={source} />{number(hazard.peak?.by_source[source])}</span>)}</div>
    <ul className="level-areas">{levels.map((level) => <li key={level.label}><span>{level.label} ≥ {level.threshold}</span><strong>{level.area_km2 > 0 ? area(level.area_km2) : "—"}</strong></li>)}</ul>
    <div className="agreement">
      <span className="agreement-label">Model agreement at ≥ {agreement.threshold}</span>
      {total > 0 ? <div className="agreement-bar" role="img" aria-label={`All ${agreement.model_count} models: ${area(agreement.all_models_km2)}; some models: ${area(agreement.some_models_km2)}`}>
        <span className="all" style={{ flexGrow: agreement.all_models_km2 }} data-tip={`All ${agreement.model_count} models: ${area(agreement.all_models_km2)}`} />
        <span className="some" style={{ flexGrow: agreement.some_models_km2 }} data-tip={`Only some models: ${area(agreement.some_models_km2)}`} />
      </div> : <div className="agreement-bar empty" />}
      <span className="agreement-legend"><i className="all" />All {agreement.model_count}: {area(agreement.all_models_km2)}<i className="some" />Some: {area(agreement.some_models_km2)}</span>
    </div>
  </button>;
}
