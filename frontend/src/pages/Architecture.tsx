import { HubOrbit } from "../components/charts";
import { PageHead } from "../components/ui";

const DIAGRAM = String.raw`                    CloudDeploy Hub
                           │
             ┌─────────────┴─────────────┐
             │                           │
        Local Project              GitHub
             │                           │
             └─────────────┬─────────────┘
                           ↓
                   Project Analyzer
                           ↓
                 Provider Compatibility
                           ↓
            ┌──────────────┼──────────────┐
            ↓              ↓              ↓
         Render         Vercel         Netlify
            ↓              ↓              ↓
        Real URL       Real URL       Real URL

            ┌──────────────┴──────────────┐
            ↓                             ↓
     GitHub Pages                  Cloudflare Pages
            ↓                             ↓
        Real URL                      Real URL`;

const LAYERS = [
  ["Frontend", "React + Vite + TypeScript, hosted on Vercel. Talks to the API with a bearer session token."],
  ["API", "FastAPI + SQLAlchemy 2.0 + Pydantic, hosted on Render. Continue with Google for sign-in; every project is private to its owner."],
  ["Database", "Supabase Postgres in production (SQLite locally). Stores users, projects, deployments, events and encrypted GitHub tokens."],
  ["Project Analyzer", "Reads manifests only (package.json, requirements.txt, Dockerfile …) to detect language, framework, build and app type. Never executes your code."],
  ["Compatibility engine", "Maps the analysis to each free platform's real capabilities: compatible, needs adaptation, or not compatible."],
  ["Providers", "One class per platform (validate, preview, deploy, get_status, get_logs, get_outputs, destroy), each using its own official mechanism."],
  ["Worker", "Polls the provider's real status, fetches its logs, then health-checks the provider-returned URL before marking SUCCESS."],
];

const PROVIDERS = [
  ["Render", "GitHub repo → POST /v1/services (free web service or static site) → Render builds → serviceDetails.url"],
  ["Vercel", "Source files → POST /v2/files → POST /v13/deployments (production) → Vercel builds → production alias"],
  ["Netlify", "Source zip (+ netlify.toml) → POST /sites/{id}/builds (Build API) → Netlify builds → site ssl_url"],
  ["GitHub Pages", "Enable Pages (Actions) → commit workflow → workflow_dispatch → deploy-pages → pages html_url"],
  ["Cloudflare Pages", "Create Pages project → Actions secrets → workflow runs wrangler pages deploy → <project>.pages.dev"],
];

export function Architecture() {
  return (
    <div className="page">
      <PageHead title="Architecture" sub="Unified Multi-Cloud Application Deployment Framework" />
      <section className="grid cols-2" style={{ alignItems: "center" }}>
        <div className="card"><pre className="code" aria-label="Architecture diagram" style={{ fontSize: 12.5 }}>{DIAGRAM}</pre></div>
        <div className="card stack" style={{ alignItems: "center", textAlign: "center" }}>
          <HubOrbit />
          <p className="muted">One project fans out from the hub to five free platforms. Each one returns its own real URL.</p>
        </div>
      </section>
      <section className="card stack">
        <h2>Layers</h2>
        <dl className="kv">{LAYERS.map(([k, v]) => <div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      </section>
      <section className="card stack">
        <h2>Deployment path per platform</h2>
        <dl className="kv">{PROVIDERS.map(([k, v]) => <div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd className="mono">{v}</dd></div>)}</dl>
      </section>
      <section className="card stack">
        <h2>Status lifecycle</h2>
        <p className="mono">QUEUED → VALIDATING → BUILDING → DEPLOYING → HEALTH_CHECKING → SUCCESS | FAILED → DESTROYING → DESTROYED</p>
        <p className="muted">Every transition comes from the provider's API response. A deployment is SUCCESS only when its public URL answers with HTTP 2xx.</p>
      </section>
    </div>
  );
}
