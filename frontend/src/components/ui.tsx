import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, CircleAlert, Eye, Info, Loader2, OctagonAlert, ShieldAlert } from "lucide-react";
import { SOURCE_META } from "../lib/format";
import type { SourceId } from "../types/synthesis";

export function Card({ title, eyebrow, actions, children, className = "" }: { title?: ReactNode; eyebrow?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>
    {(title || eyebrow || actions) && <header className="card-head">
      <div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}{title && <h2>{title}</h2>}</div>
      {actions && <div className="card-actions">{actions}</div>}
    </header>}
    {children}
  </section>;
}

export function Stat({ label, value, unit, detail, tone }: { label: string; value: ReactNode; unit?: string; detail?: ReactNode; tone?: "good" | "warn" | "muted" }) {
  return <div className={`stat ${tone ?? ""}`}>
    <span className="stat-label">{label}</span>
    <strong className="stat-value">{value}{unit && <small>{unit}</small>}</strong>
    {detail && <span className="stat-detail">{detail}</span>}
  </div>;
}

export function Segmented<T extends string | number>({ value, options, onChange, label, size }: {
  value: T;
  options: { value: T; label: ReactNode; disabled?: boolean; title?: string }[];
  onChange: (value: T) => void;
  label: string;
  size?: "small";
}) {
  return <div className={`segmented ${size ?? ""}`} role="group" aria-label={label}>
    {options.map((option) => <button key={String(option.value)} className={option.value === value ? "active" : ""} disabled={option.disabled} title={option.title} onClick={() => onChange(option.value)}>{option.label}</button>)}
  </div>;
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return <div className="field"><span className="field-label">{label}</span>{children}{hint && <span className="field-hint">{hint}</span>}</div>;
}

export function SourceTag({ source, withKind = false }: { source: SourceId; withKind?: boolean }) {
  const meta = SOURCE_META[source];
  return <span className="source-tag"><i style={{ background: meta.color }} />{meta.short}{withKind && <em>{meta.kind}</em>}</span>;
}

const LEVEL_TONES = ["warning", "serious", "critical"] as const;
const LEVEL_ICONS = { warning: CircleAlert, serious: AlertTriangle, critical: OctagonAlert };

/** Hazard severity: reserved status colour plus icon plus label, never colour alone. */
export function LevelChip({ level, levels, watch }: { level: string | null | undefined; levels: string[]; watch?: string | null }) {
  if (!level && watch) return <span className="level-chip watch" title={`Single-model signal: ${watch}`}><Eye size={13} />Watch</span>;
  if (!level) return <span className="level-chip none"><CheckCircle2 size={13} />Below threshold</span>;
  const tone = LEVEL_TONES[Math.max(0, Math.min(2, levels.indexOf(level)))];
  const Icon = LEVEL_ICONS[tone];
  return <span className={`level-chip ${tone}`}><Icon size={13} />{level}</span>;
}

export function Notice({ tone = "info", title, children, action }: { tone?: "info" | "warn" | "error"; title: string; children?: ReactNode; action?: ReactNode }) {
  const Icon = tone === "error" ? ShieldAlert : tone === "warn" ? AlertTriangle : Info;
  return <div className={`notice ${tone}`}><Icon size={17} /><div><strong>{title}</strong>{children && <p>{children}</p>}{action}</div></div>;
}

export function Loading({ label, detail }: { label: string; detail?: string }) {
  return <div className="loading"><Loader2 className="spin" size={22} /><strong>{label}</strong>{detail && <span>{detail}</span>}</div>;
}

export function StatusDot({ ok, label }: { ok: boolean | null; label: string }) {
  return <span className={`status-dot-label ${ok === null ? "pending" : ok ? "ok" : "down"}`}><i />{label}</span>;
}

export function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return <dl className="kv">{items.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value ?? "—"}</dd></div>)}</dl>;
}
