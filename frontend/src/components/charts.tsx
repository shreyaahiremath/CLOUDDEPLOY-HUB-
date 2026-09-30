// Animated charts and looping illustrations. Charts render real numbers only; HubOrbit is a
// decorative illustration of how the hub routes an app to the five platforms.
import { useEffect, useState } from "react";
import { cookiePath } from "./Logo";
import { PROVIDER_META, ProviderMark } from "./ui";

export interface DayPoint { date: string; total: number; success: number; failed: number }

const W = 600, H = 190, PAD_X = 12, PAD_TOP = 16, PAD_BOTTOM = 26;

function smooth(points: [number, number][]): string {
  return points.reduce((d, [x, y], i) => {
    if (i === 0) return `M${x} ${y}`;
    const [px, py] = points[i - 1];
    const mx = (px + x) / 2;
    return `${d} C${mx} ${py} ${mx} ${y} ${x} ${y}`;
  }, "");
}

export function AreaChart({ data }: { data: DayPoint[] }) {
  const max = Math.max(1, ...data.map((d) => d.total));
  const step = (W - PAD_X * 2) / Math.max(1, data.length - 1);
  const y = (v: number) => PAD_TOP + (1 - v / max) * (H - PAD_TOP - PAD_BOTTOM);
  const totals = data.map((d, i): [number, number] => [PAD_X + i * step, y(d.total)]);
  const wins = data.map((d, i): [number, number] => [PAD_X + i * step, y(d.success)]);
  const line = smooth(totals);
  const area = `${line} L${W - PAD_X} ${H - PAD_BOTTOM} L${PAD_X} ${H - PAD_BOTTOM} Z`;
  const sum = data.reduce((n, d) => n + d.total, 0);
  const fmt = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
  const summary = `Deployments per day for the last ${data.length} days: ${sum} in total, busiest day ${max === 1 && sum === 0 ? 0 : max}.`;

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary}>
      <defs>
        <linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--md-primary)" stopOpacity="0.38" />
          <stop offset="100%" stopColor="var(--md-primary)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 0.5, 1].map((f) => (
        <line key={f} className="grid-line" x1={PAD_X} x2={W - PAD_X} y1={y(max * f)} y2={y(max * f)} />
      ))}
      <path className="area" d={area} />
      <path className="line second" d={smooth(wins)} pathLength={1} />
      <path className="line" d={line} pathLength={1} />
      {totals.map(([px, py], i) => data[i].total > 0 && (
        <circle key={i} className="pt" cx={px} cy={py} r="4" style={{ animationDelay: `${600 + i * 40}ms`, transformOrigin: `${px}px ${py}px` }}>
          <title>{`${fmt(data[i].date)}: ${data[i].total} deployment(s), ${data[i].success} live, ${data[i].failed} failed`}</title>
        </circle>
      ))}
      {/* a dot that keeps travelling the line */}
      <circle className="runner" r="5" style={{ offsetPath: `path("${line}")` }} />
      <text className="axis" x={PAD_X} y={H - 6}>{data.length ? fmt(data[0].date) : ""}</text>
      <text className="axis" x={W - PAD_X} y={H - 6} textAnchor="end">Today</text>
      <text className="axis" x={W - PAD_X} y={PAD_TOP - 4} textAnchor="end">{max} / day</text>
    </svg>
  );
}

export function Donut({ success, failed }: { success: number; failed: number }) {
  const done = success + failed;
  const pct = done ? success / done : 0;
  const R = 52, C = 2 * Math.PI * R;
  const [shown, setShown] = useState(0);
  useEffect(() => { const id = requestAnimationFrame(() => setShown(pct)); return () => cancelAnimationFrame(id); }, [pct]);
  const label = done ? `${Math.round(pct * 100)}% of finished deployments succeeded (${success} of ${done}).` : "No finished deployments yet.";

  return (
    <div className="donut" role="img" aria-label={label}>
      <svg viewBox="0 0 140 140">
        <circle className="orbit" cx="70" cy="70" r="66" fill="none" strokeWidth="2" strokeLinecap="round" />
        <circle className="track" cx="70" cy="70" r={R} fill="none" strokeWidth="14" />
        {done > 0 && failed > 0 && (
          <circle className="arc rest" cx="70" cy="70" r={R} fill="none" strokeWidth="14" strokeDasharray={C} strokeDashoffset={0} />
        )}
        {done > 0 && (
          <circle className="arc" cx="70" cy="70" r={R} fill="none" strokeWidth="14" strokeDasharray={C} strokeDashoffset={C * (1 - shown)} />
        )}
      </svg>
      <div className="center">
        <b>{done ? `${Math.round(pct * 100)}%` : "–"}</b>
        <span>{done ? "success rate" : "no results yet"}</span>
      </div>
    </div>
  );
}

export function ProviderBars({ items }: { items: { provider: string; name: string; total: number; success: number }[] }) {
  const max = Math.max(1, ...items.map((i) => i.total));
  const [grown, setGrown] = useState(false);
  useEffect(() => { const id = requestAnimationFrame(() => setGrown(true)); return () => cancelAnimationFrame(id); }, []);
  return (
    <div className="bars">
      {items.map((it) => (
        <div key={it.provider} className="bar-row">
          <ProviderMark provider={it.provider} size={28} />
          <div>
            <div className="bar-name"><span>{it.name}</span></div>
            <div className="bar-track" role="img" aria-label={`${it.name}: ${it.total} deployments, ${it.success} live`}>
              <div className="bar-fill" style={{ width: grown ? `${(it.total / max) * 100}%` : 0 }} />
            </div>
          </div>
          <span className="subtle" style={{ fontVariantNumeric: "tabular-nums" }}>{it.total}{it.success ? ` · ${it.success} live` : ""}</span>
        </div>
      ))}
    </div>
  );
}

/** M3 Expressive wavy linear progress (indeterminate). */
export function WavyProgress({ label = "In progress" }: { label?: string }) {
  let d = "M-24 6";
  for (let x = -24; x < 264; x += 24) d += ` Q${x + 6} 1.5 ${x + 12} 6 T${x + 24} 6`;
  return (
    <svg className="wavy" viewBox="0 0 240 12" preserveAspectRatio="none" role="progressbar" aria-label={label}>
      <line className="track" x1="0" x2="240" y1="6" y2="6" strokeWidth="4" strokeLinecap="round" />
      <path className="wave" d={d} fill="none" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

const ORDER = ["render", "vercel", "netlify", "github_pages", "cloudflare_pages"];
const CORE = cookiePath(190, 190, 40, 9, 0.09);

/** Looping illustration: packets flow from the hub to each free platform. */
export function HubOrbit() {
  const nodes = ORDER.map((key, i) => {
    const a = (-90 + i * 72) * (Math.PI / 180);
    return { key, x: 190 + 140 * Math.cos(a), y: 190 + 140 * Math.sin(a), meta: PROVIDER_META[key] };
  });
  return (
    <svg className="hub" viewBox="0 0 380 392" aria-hidden="true">
      {[0, 1.06, 2.12].map((delay) => <circle key={delay} className="ring" cx="190" cy="190" r="42" style={{ animationDelay: `${delay}s` }} />)}
      {nodes.map((n, i) => {
        const path = `M190 190 L${n.x.toFixed(1)} ${n.y.toFixed(1)}`;
        return (
          <g key={n.key}>
            <path className="link" d={path} />
            <circle className="packet" r="5" style={{ offsetPath: `path("${path}")`, animationDelay: `${i * 0.52}s` }} />
            <circle className="packet" r="3.5" style={{ offsetPath: `path("${path}")`, animationDelay: `${i * 0.52 + 1.3}s` }} />
          </g>
        );
      })}
      <path className="core" d={CORE} />
      <g className="core-glyph" strokeWidth="4" strokeLinecap="round" fill="none">
        <path d="M180 190 203 176M180 190h26M180 190 203 204" />
      </g>
      <circle className="core-glyph" cx="177" cy="190" r="8" />
      {nodes.map((n, i) => (
        <g key={n.key} className="bob" style={{ animationDelay: `${i * 0.6}s` }}>
          <circle className="node" cx={n.x} cy={n.y} r="26" style={{ fill: n.meta.color, stroke: "none" }} />
          <text className="node-text" x={n.x} y={n.y} style={{ fill: n.meta.on }}>{n.meta.mono}</text>
          <text className="node-label" x={n.x} y={n.y + 42}>{n.meta.name}</text>
        </g>
      ))}
    </svg>
  );
}
