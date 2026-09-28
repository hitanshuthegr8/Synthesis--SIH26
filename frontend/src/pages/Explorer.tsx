import { useEffect, useMemo, useState } from "react";
import { Crosshair, Layers, Scale } from "lucide-react";
import { synthesis } from "../api";
import { useApp } from "../app/context";
import { WeightBar } from "../components/charts";
import { SpatialFieldMap } from "../components/SpatialFieldMap";
import type { FieldPalette } from "../components/fieldPalette";
import { Card, Field, KeyValue, Loading, Notice, Segmented, SourceTag } from "../components/ui";
import { SOURCE_META, SOURCE_ORDER, VARIABLE_META, coordinate, number, signed, unitLabel, validLabel } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import type { LayerId, PointExplanation, SourceId, VariableId, Weighting } from "../types/synthesis";

const LAYERS: { id: LayerId; label: string }[] = [
  { id: "blend", label: "AIRAVAT blend" },
  { id: "GFS", label: "GFS" },
  { id: "ECMWF", label: "IFS" },
  { id: "AIFS", label: "AIFS" },
  { id: "spread", label: "Model spread" },
  { id: "weights", label: "Weight map" },
];

export function Explorer() {
  const { cycle, catalog, params } = useApp();
  const [variable, setVariable] = useState<VariableId>((params.get("variable") as VariableId) || "temperature");
  const [lead, setLead] = useState(Number(params.get("lead")) || 24);
  const [layer, setLayer] = useState<LayerId>((params.get("layer") as LayerId) || "blend");
  const [weightSource, setWeightSource] = useState<SourceId>("ECMWF");
  const verifiable = catalog?.variables.find((item) => item.id === variable)?.verifiable ?? (variable === "temperature" || variable === "wind_speed");
  const [weightingChoice, setWeighting] = useState<Weighting>("adaptive");
  const weighting: Weighting = verifiable ? weightingChoice : "equal";
  const [cell, setCell] = useState<{ latitude: number; longitude: number } | null>(null);

  const meta = VARIABLE_META[variable];
  useEffect(() => { if (!meta.leads.includes(lead)) setLead(meta.leads[0]); }, [variable]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!verifiable && layer === "weights") setLayer("blend"); }, [verifiable, layer]);

  const field = useAsync(
    () => synthesis.field({ variable, lead, layer, weighting, source: layer === "weights" ? weightSource : undefined, initialization: cycle }),
    [variable, lead, layer, weighting, weightSource, cycle],
  );
  const point = useAsync<PointExplanation>(
    cell ? () => synthesis.point(variable, lead, cell.latitude, cell.longitude, cycle) : null,
    [cell?.latitude, cell?.longitude, variable, lead, cycle],
  );

  const palette: FieldPalette = layer === "spread" ? "spread" : layer === "weights" ? `weight_${weightSource}` : meta.palette;
  const scale = layer === "blend" || SOURCE_ORDER.includes(layer as SourceId) ? meta.scale : "linear";
  const title = layer === "weights" ? `${SOURCE_META[weightSource].label} weight` : layer === "spread" ? `Model spread · ${meta.label}` : `${LAYERS.find((item) => item.id === layer)?.label} · ${meta.label}`;
  const provenance = field.data?.provenance as Record<string, unknown> | undefined;
  const unavailableReason = field.data?.status === "UNAVAILABLE" ? field.data.reason : undefined;
  const adaptiveMissing = unavailableReason && weighting === "adaptive" && (layer === "blend" || layer === "weights");

  return <div className="page explorer">
    <aside className="rail">
      <Card eyebrow="REQUEST" title="Blend explorer">
        <Field label="Variable">
          <div className="stack-options">{(Object.keys(VARIABLE_META) as VariableId[]).map((id) => <button key={id} className={`option ${variable === id ? "active" : ""}`} onClick={() => { setVariable(id); setCell(null); }}>
            <strong>{VARIABLE_META[id].short}</strong><span>{VARIABLE_META[id].label} · {unitLabel(VARIABLE_META[id].units)}</span>
          </button>)}</div>
        </Field>
        <Field label="Lead time" hint={validLabel(field.data?.initialization ?? cycle, lead)}>
          <Segmented label="Lead time" value={lead} onChange={(value) => { setLead(value); setCell(null); }} options={meta.leads.map((value) => ({ value, label: `${value}h` }))} />
        </Field>
        <Field label="Layer">
          <div className="layer-list">{LAYERS.map((item) => <button key={item.id} className={`layer ${layer === item.id ? "active" : ""}`} disabled={item.id === "weights" && !verifiable} title={item.id === "weights" && !verifiable ? "Weight maps need a verifiable variable (temperature or wind)" : undefined} onClick={() => setLayer(item.id)}>
            {SOURCE_ORDER.includes(item.id as SourceId) ? <SourceTag source={item.id as SourceId} withKind /> : <span className="layer-name">{item.id === "blend" ? <Layers size={13} /> : item.id === "spread" ? <Crosshair size={13} /> : <Scale size={13} />}{item.label}</span>}
          </button>)}</div>
        </Field>
        {layer === "weights" && <Field label="Weight of">
          <Segmented label="Weight source" value={weightSource} onChange={setWeightSource} options={SOURCE_ORDER.map((source) => ({ value: source, label: SOURCE_META[source].short }))} />
        </Field>}
        {layer === "blend" && <Field label="Weighting" hint={verifiable ? "Adaptive = per-cell bias correction + skill weights" : "Rainfall and max temperature have no verifying reference yet, so they use equal weights"}>
          <Segmented label="Weighting" value={weighting} onChange={setWeighting} options={[{ value: "adaptive", label: "Adaptive", disabled: !verifiable }, { value: "equal", label: "Equal" }]} />
        </Field>}
      </Card>
    </aside>

    <section className="map-column">
      {field.status === "loading" && !field.data
        ? <Card><Loading label="Fetching live model fields…" detail="A cold cycle downloads GFS, IFS and AIFS GRIB and replays past cycles for skill; the first load can take a minute." /></Card>
        : field.status === "error"
          ? <Notice tone="error" title="Field request failed" action={<button className="btn ghost" onClick={field.reload}>Retry</button>}>{field.error}</Notice>
          : <>
            {adaptiveMissing && <Notice tone="warn" title="Adaptive weights are not available for this request" action={<button className="btn ghost" onClick={() => setWeighting("equal")}>Show the equal-weight blend</button>}>{unavailableReason}</Notice>}
            <div className={`map-stage${field.status === "loading" ? " refreshing" : ""}`}>
              <SpatialFieldMap field={field.data} title={title} palette={palette} scale={scale} onCellSelect={(_, latitude, longitude) => setCell({ latitude, longitude })} />
              {field.status === "loading" && <div className="stage-overlay"><Loading label="Updating…" /></div>}
            </div>
            {provenance && field.data?.status === "AVAILABLE" && <LayerFacts provenance={provenance} summary={field.data.summary} units={field.data.units ?? ""} />}
          </>}
    </section>

    <aside className="rail right">
      <CellBreakdown point={point.data} loading={point.status === "loading"} error={point.error} hasCell={Boolean(cell)} />
    </aside>
  </div>;
}

function LayerFacts({ provenance, summary, units }: { provenance: Record<string, unknown>; summary?: { india_min: number; india_max: number; india_mean: number }; units: string }) {
  const weights = provenance.source_weights as Partial<Record<SourceId, number>> | undefined;
  const bias = provenance.bias_correction as Partial<Record<SourceId, number>> | undefined;
  const missing = provenance.missing_sources as Record<string, string> | undefined;
  const missingEntries = Object.entries(missing ?? {}).filter(([, reason]) => reason !== "disabled");
  const unit = units === "weight" ? "" : ` ${unitLabel(units)}`;
  return <div className="facts-grid">
    <Card eyebrow="THIS LAYER" className="facts">
      <KeyValue items={[
        ["Valid", validLabel(provenance.initialization as string, provenance.lead_hours as number)],
        ["India mean", summary ? (units === "weight" ? `${(summary.india_mean * 100).toFixed(0)}%` : `${number(summary.india_mean)}${unit}`) : "—"],
        ["Weight policy", (provenance.weight_policy as string) ?? (provenance.definition as string) ?? (provenance.kind as string) ?? "Single model"],
        ["Skill sample", provenance.skill_samples ? `${provenance.skill_samples} past cycles` : "—"],
      ]} />
      {typeof provenance.variable_note === "string" && <p className="fine">{provenance.variable_note}</p>}
    </Card>
    {weights && <Card eyebrow="INDIA-MEAN WEIGHTS">
      <WeightBar weights={weights} label="India-mean weights" />
      {bias && <div className="bias-row">{SOURCE_ORDER.filter((source) => bias[source] !== undefined).map((source) => <span key={source}><SourceTag source={source} /> bias {signed(bias[source] ?? 0, 2)}{unit}</span>)}</div>}
      {missingEntries.length > 0 && <p className="fine warn">Not in this blend: {missingEntries.map(([source, reason]) => `${source} (${reason})`).join("; ")}</p>}
    </Card>}
  </div>;
}

function CellBreakdown({ point, loading, error, hasCell }: { point: PointExplanation | null; loading: boolean; error: string | null; hasCell: boolean }) {
  const rows = useMemo(() => [...(point?.sources ?? [])].sort((a, b) => SOURCE_ORDER.indexOf(a.source) - SOURCE_ORDER.indexOf(b.source)), [point]);
  if (!hasCell) return <Card eyebrow="CELL BREAKDOWN" title="Click the map">
    <p className="muted-text">Pick any grid cell to see how AIRAVAT builds its value there: each model's forecast, the bias it is corrected for, the weight it earns, and its contribution to the blend.</p>
  </Card>;
  if (loading && !point) return <Card eyebrow="CELL BREAKDOWN"><Loading label="Explaining this cell…" /></Card>;
  if (error) return <Card eyebrow="CELL BREAKDOWN"><Notice tone="error" title="Could not explain this cell">{error}</Notice></Card>;
  if (!point || point.status !== "AVAILABLE") return <Card eyebrow="CELL BREAKDOWN"><Notice tone="warn" title="No breakdown">{point?.reason}</Notice></Card>;
  const unit = unitLabel(point.units);
  const adaptive = point.adaptive_blend;
  return <Card eyebrow="CELL BREAKDOWN" title={<>{number(adaptive ?? point.equal_blend)} <small>{unit}</small></>} className="breakdown">
    <p className="muted-text">{coordinate(point.latitude, point.longitude)}{point.region ? ` · ${point.region}` : point.inside_india ? "" : " · outside India"}</p>
    <table className="breakdown-table">
      <thead><tr><th>Model</th><th>Raw</th><th>Bias</th><th>Weight</th><th>Adds</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.source}>
        <td><SourceTag source={row.source} /></td>
        <td>{number(row.value)}</td>
        <td>{row.bias !== undefined ? signed(row.bias, 2) : "—"}</td>
        <td>{row.weight !== undefined ? <span className="weight-cell"><span style={{ width: `${row.weight * 100}%`, background: SOURCE_META[row.source].color }} />{Math.round(row.weight * 100)}%</span> : "—"}</td>
        <td>{row.contribution !== undefined ? number(row.contribution, 2) : "—"}</td>
      </tr>)}</tbody>
    </table>
    <KeyValue items={[
      ["AIRAVAT (adaptive)", adaptive !== null ? `${number(adaptive)} ${unit}` : "—"],
      ["Equal-weight mean", `${number(point.equal_blend)} ${unit}`],
      ["Model spread", `${number(point.spread)} ${unit}`],
      ["Skill history", point.skill_samples ? `${point.skill_samples} past cycles` : "none"],
    ]} />
    {point.skill_reason && <p className="fine">{point.skill_reason}</p>}
  </Card>;
}
