# Changelog

## 1.2.0 (2026-09-30)

Material You (Material 3 Expressive) redesign. No feature or route was removed.

- Dynamic colour: the whole palette is generated from a seed hue in OKLCH; six themes (Aurora default,
  Ocean, Forest, Sunset, Blossom, Orchid) selectable in the drawer and in Settings.
- New logo: rotating Material "cookie" shape with a hub mark; matching favicon.
- Dashboard: animated area chart (last 14 days), success-rate ring, per-platform bars, all from real
  counts (`/api/stats` now returns `timeline` and `by_provider`), plus the looping hub illustration.
- Components: extended FAB, ripple, filter chips (History), wavy progress, shape-morphing loader,
  Material confirm dialogs (replace browser pop-ups), bottom navigation on phones.
- Motion: drifting aurora, flowing wave on the route strip, staggered entrances; disabled under
  `prefers-reduced-motion`. The app is dark only.

## 1.1.0 (2026-09-30)

- Database: Supabase is now used through its HTTPS API (project URL + secret key) instead of a Postgres
  connection string. No database password, no `DATABASE_URL`, no Postgres driver.
- Uploaded project zips are stored in a private Supabase Storage bucket.
- `/api/health` and the Settings page report the database connection state and any problem in plain words.
- Timestamps sent to the browser are always UTC-aware.
- Deploy wiring: `frontend/.env.production`, root `requirements.txt`, GitHub Actions CI.

## 1.0.0 (2026-09-30)

Initial release of CloudDeploy Hub, the Unified Multi-Cloud Application Deployment Framework.

- FastAPI backend (SQLAlchemy 2.0, Pydantic) with Supabase Postgres support and SQLite for local dev.
- Continue with Google sign-in; per-user projects, GitHub connections and deployments.
- GitHub integration: username field + OAuth (repo, workflow, read:user), repository/branch browser,
  mismatch warning, encrypted token, revoke on disconnect, publish uploads via the Git Data API.
- Local upload (folder / zip) with traversal, size, `.env`, secret and executable validation;
  uploads persisted in the database to survive ephemeral disks.
- Project Analyzer, provider compatibility engine, Dockerfile validation/generation.
- Real providers: Render (API), Vercel (API file upload), Netlify (Build API), GitHub Pages
  (Actions + deploy-pages), Cloudflare Pages (API + Actions + wrangler).
- Background worker with real status polling, provider logs, health checks, redeploy, destroy,
  resume after restart, and provider end-to-end verification tracking.
- React + Vite + TypeScript frontend with all pages, light/dark themes, and the live route strip.
- Deploy configs: `render.yaml` (backend), `frontend/vercel.json` (frontend).
- 47 backend tests; `scripts/acceptance_test.py` for real provider verification.
- Docs: architecture, deployment guide, GitHub integration, provider guide, troubleshooting,
  FAQs, project report content.
