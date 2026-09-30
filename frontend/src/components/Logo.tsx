// CloudDeploy Hub mark: a Material "cookie" shape (slowly rotating) holding a hub that fans out
// to three destinations. Colours come from the active dynamic-colour scheme.

/** Scalloped Material shape as an SVG path. */
export function cookiePath(cx: number, cy: number, radius: number, lobes = 9, depth = 0.085, steps = 120): string {
  const pts: string[] = [];
  for (let i = 0; i < steps; i++) {
    const t = (i / steps) * Math.PI * 2;
    const r = radius * (1 + depth * Math.cos(lobes * t));
    pts.push(`${(cx + r * Math.cos(t)).toFixed(2)} ${(cy + r * Math.sin(t)).toFixed(2)}`);
  }
  return `M${pts.join("L")}Z`;
}

const COOKIE = cookiePath(24, 24, 20.5);

export function Logo({ size = 36 }: { size?: number }) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <path className="cookie" d={COOKIE} />
      <g className="glyph" strokeWidth="2.4" strokeLinecap="round" fill="none">
        <path d="M18.5 24 30 16.5M18.5 24h13M18.5 24 30 31.5" />
      </g>
      <circle className="glyph" cx="17" cy="24" r="4.2" />
      <circle className="glyph" cx="31" cy="16" r="2.8" />
      <circle className="glyph" cx="32.5" cy="24" r="2.8" />
      <circle className="spark" cx="31" cy="32" r="3.2" />
    </svg>
  );
}
