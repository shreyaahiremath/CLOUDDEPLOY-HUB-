# Changelog

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
