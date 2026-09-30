import { useState, type ReactNode } from "react";
import { ACTIVE, type Deployment, type Status } from "../api";
import { IconAlert, IconCheck, IconInfo, IconX } from "./icons";

export const PROVIDER_META: Record<string, { name: string; mono: string; color: string }> = {
  render: { name: "Render", mono: "Rd", color: "#4b5563" },
  vercel: { name: "Vercel", mono: "Vc", color: "#1f2937" },
  netlify: { name: "Netlify", mono: "Nf", color: "#0f766e" },
  github_pages: { name: "GitHub Pages", mono: "GP", color: "#6d28d9" },
  cloudflare_pages: { name: "Cloudflare Pages", mono: "CF", color: "#c2410c" },
};

export function ProviderMark({ provider, size = 40 }: { provider: string; size?: number }) {
  const meta = PROVIDER_META[provider] ?? { mono: "?", color: "#6b7280" };
  return (
    <span className="monogram" style={{ background: meta.color, width: size, height: size, fontSize: size * 0.38 }} aria-hidden="true">
      {meta.mono}
    </span>
  );
}

export const providerName = (key: string) => PROVIDER_META[key]?.name ?? key;

const STATUS_LABEL: Record<Status, string> = {
  QUEUED: "Queued", VALIDATING: "Validating", BUILDING: "Building", DEPLOYING: "Deploying",
  HEALTH_CHECKING: "Health check", SUCCESS: "Live", FAILED: "Failed", DESTROYING: "Destroying", DESTROYED: "Destroyed",
};

export function StatusBadge({ status }: { status: Status }) {
  const tone = status === "SUCCESS" ? "live" : status === "FAILED" ? "danger" : status === "DESTROYED" ? "" : "info";
  const active = ACTIVE.includes(status);
  return (
    <span className={`badge ${tone} ${active ? "pulse" : ""}`}>
      <span className="dot" />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function HealthBadge({ d }: { d: Pick<Deployment, "health_status" | "health_detail"> }) {
  if (d.health_status === "healthy") return <span className="badge success" title={d.health_detail ?? ""}><IconCheck size={12} />Healthy</span>;
  if (d.health_status === "unreachable") return <span className="badge danger" title={d.health_detail ?? ""}><IconX size={12} />Unreachable</span>;
  return <span className="badge">Not checked</span>;
}

export function Alert({ tone = "info", title, children }: { tone?: "info" | "warning" | "danger" | "success"; title?: ReactNode; children?: ReactNode }) {
  const Icon = tone === "success" ? IconCheck : tone === "info" ? IconInfo : IconAlert;
  return (
    <div className={`alert ${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <Icon />
      <div className="stack" style={{ gap: 4 }}>
        {title && <strong>{title}</strong>}
        {children && <div>{children}</div>}
      </div>
    </div>
  );
}

export function PageHead({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </header>
  );
}

export function Empty({ icon, title, children, action }: { icon: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="card empty">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      {children && <p style={{ maxWidth: 440 }}>{children}</p>}
      {action}
    </div>
  );
}

export function Skeleton({ h = 16, w = "100%" }: { h?: number; w?: number | string }) {
  return <div className="skeleton" style={{ height: h, width: w }} aria-hidden="true" />;
}

export function CardSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="card stack" aria-busy="true" aria-label="Loading">
      <Skeleton h={20} w="40%" />
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} w={`${90 - i * 12}%`} />)}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Alert tone="danger" title="Couldn't load this">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span>{message}</span>
        {onRetry && <button className="btn sm" onClick={onRetry}>Try again</button>}
      </div>
    </Alert>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="btn sm"
      onClick={async () => {
        try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1600); } catch { /* clipboard blocked */ }
      }}
      aria-label={`${label}: ${text}`}
    >
      {done ? "Copied" : label}
    </button>
  );
}

export function Spinner({ label }: { label?: string }) {
  return <span className="row" role="status"><span className="spinner" aria-hidden="true" />{label && <span>{label}</span>}</span>;
}
