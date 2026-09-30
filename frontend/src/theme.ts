// Material You dynamic colour: a theme is a seed hue + an accent hue. Every colour in styles.css
// is derived from these two CSS variables in OKLCH.
export interface Scheme { key: string; name: string; hue: number; hue3: number }

// Accent hues stay well away from red (hue ~25) so "live" never reads as an error.
export const SCHEMES: Scheme[] = [
  { key: "aurora", name: "Aurora", hue: 190, hue3: 300 },
  { key: "ocean", name: "Ocean", hue: 255, hue3: 165 },
  { key: "forest", name: "Forest", hue: 150, hue3: 230 },
  { key: "sunset", name: "Sunset", hue: 70, hue3: 310 },
  { key: "blossom", name: "Blossom", hue: 340, hue3: 200 },
  { key: "orchid", name: "Orchid", hue: 305, hue3: 190 },
];

const KEY = "cdh_scheme";

export function currentScheme(): Scheme {
  let saved: string | null = null;
  try { saved = localStorage.getItem(KEY); } catch { /* storage blocked */ }
  return SCHEMES.find((s) => s.key === saved) ?? SCHEMES[0];
}

export function applyScheme(scheme: Scheme, persist = true): void {
  const root = document.documentElement;
  root.style.setProperty("--hue", String(scheme.hue));
  root.style.setProperty("--hue-3", String(scheme.hue3));
  if (persist) { try { localStorage.setItem(KEY, scheme.key); } catch { /* storage blocked */ } }
}
