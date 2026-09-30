# Unified Multi-Cloud Application Deployment Framework (CloudDeploy Hub)

*Project report content. Sections 22–23 must be completed with results from real test runs; nothing
here is invented.*

## 1. Abstract
Deploying a web application requires learning each hosting provider's workflow, build settings and
limits. CloudDeploy Hub is a web platform that accepts a user's own project (a GitHub repository or an
uploaded folder), statically analyzes it, determines which free cloud platforms can run it, and
deploys it through the official API of the selected platform: Render, Vercel, Netlify, GitHub Pages or
Cloudflare Pages. The system reports real provider status and logs and marks a deployment successful
only after the provider-returned public URL passes an HTTP health check.

## 2. Introduction
Students and small teams usually deploy on free tiers, but each provider differs in build model
(native runtime, Docker, static build, serverless), source model (Git, file upload) and constraints.
CloudDeploy Hub provides one consistent workflow over these differences while respecting what each
platform actually supports.

## 3. Problem Statement
Choosing an incompatible platform (for example a FastAPI backend on a static host), misconfiguring
build commands, or leaking secrets during deployment are common failures. Existing dashboards are
provider-specific and do not tell a user *whether* their project can run on a given free platform.

## 4. Existing System
Each provider has its own dashboard and CLI (Render Dashboard, Vercel CLI, Netlify CLI, wrangler,
GitHub Actions). Users must configure each separately, and none compares providers or checks
compatibility across them. Multi-cloud tools such as Terraform target paid infrastructure and require
infrastructure-as-code expertise.

## 5. Proposed System
A single web application with Google sign-in, GitHub OAuth, local upload, a project analyzer, a
provider compatibility engine, a common provider abstraction with five real implementations, a
background deployment worker, health checks, logs, deployment history and resource destruction.

## 6. Objectives
1. Deploy a user's own project to multiple free platforms from one interface.
2. Detect language, framework and application type automatically.
3. Offer only platforms whose free plan can run the project, with reasons.
4. Use official provider APIs and return real URLs, statuses and logs.
5. Protect credentials and user code throughout.

## 7. Literature Survey
*(Add academic/industry sources your guide requires.)* Relevant areas: Platform-as-a-Service models;
the Twelve-Factor App methodology (configuration via environment, port binding); container-based
deployment (Docker); static site generation and CDNs; serverless computing; OAuth 2.0 (RFC 6749) and
OpenID Connect; multi-cloud abstraction layers.

## 8. Feasibility Study
- **Technical:** all five providers expose documented REST APIs or official CLIs usable from CI.
- **Economic:** every component runs on free tiers (Vercel, Render, Supabase, provider free plans).
- **Operational:** users need only a browser, a Google account, and provider accounts.

## 9. Architecture
See `docs/architecture.md`: React frontend (Vercel) → FastAPI backend (Render) → Supabase Postgres;
analyzer → compatibility engine → provider implementations → worker → health check.

## 10. Requirements
**Functional:** Google sign-in; GitHub username + OAuth; repository/branch browsing; folder/zip upload
with validation; publish upload to GitHub; analysis; compatibility; preview; deploy; status; logs;
health check; history; redeploy; destroy.
**Non-functional:** no secrets in frontend; encrypted token storage; per-user data isolation; responsive
UI with dark mode and keyboard access; resumable deployments after restart.
**Software:** Python 3.12, Node 20, modern browser. **Hardware:** none beyond a client device.

## 11. Technology Stack
FastAPI, SQLAlchemy 2.0, Pydantic, httpx, PyNaCl, cryptography (Fernet), Supabase REST + Storage APIs; React 19, Vite,
TypeScript, React Router; Supabase (database and file storage); GitHub Actions; pytest + respx.

## 12. GitHub Integration
Username field (identity only) with existence check; OAuth authorization-code flow with single-use
state bound to the signed-in user; scopes `repo workflow read:user`; encrypted token; mismatch warning;
repository and branch listing; publishing uploads via the Git Data API; token revocation on disconnect.

## 13. Project Analysis
Reads manifests only: `package.json`, lockfiles, `requirements.txt`, `pyproject.toml`, `Pipfile`,
`Dockerfile`, framework configs, entry files. Detects language, framework (FastAPI, Flask, Django,
Express, NestJS, React/Vite, CRA, Next.js, Vue, Svelte, Angular, Astro, static HTML, Go, Java …), app
type (Static Frontend, Frontend, Serverless, Backend API, Full Stack, Worker, Unknown), install/build/
start commands, output directory and Python ASGI/WSGI entry point; validates Dockerfiles.

## 14. Provider Compatibility
A rule engine maps each app category to each provider's real free-plan capability and returns
*compatible*, *conditional* (needs adaptation, requires explicit acknowledgement) or *incompatible*
(not selectable), always with reasons.

## 15. Free Cloud Deployment
Only providers with free options are included. The UI never promises unlimited usage. It shows
"Free plan available subject to the provider's current limits and terms".

## 16. Render Implementation
`POST /v1/services` with `plan: free`, native runtime or Docker, env vars, SPA rewrites for static
sites; deploy status polling; logs API; URL from `serviceDetails.url`; `DELETE` to destroy.

## 17. Vercel Implementation
Content-addressed file upload (`/v2/files`, SHA-1), project creation, production deployment
(`/v13/deployments`), `readyState` polling, build events as logs, production alias as URL.

## 18. Netlify Implementation
Site creation and the Build API (multipart source zip) so Netlify performs the build; generated
`netlify.toml` when absent; deploy state polling; site `ssl_url` as URL.

## 19. GitHub Pages Implementation
Pages enabled with `build_type: workflow`; generated workflow using `upload-pages-artifact` and
`deploy-pages`; automatic base path for Vite/CRA; SPA 404 fallback; run tracking and job logs.

## 20. Cloudflare Pages Implementation
Pages project creation via the Cloudflare API; credentials stored as encrypted GitHub Actions secrets
(libsodium sealed box); workflow running `wrangler pages deploy`; status from the run and Cloudflare's
deployment stage.

## 21. Security
Secrets only in backend env; Fernet-encrypted GitHub tokens and env-var values; hashed session tokens;
single-use OAuth state; upload validation (path traversal, size, `.env`, key files, secret patterns,
executables); zip-bomb guard; no execution of user code; per-user query scoping; security headers on
the frontend.

## 22. Testing
Automated (pytest, 54 tests, all passing at the time of writing):
- Project: upload (folder and zip), validation, path traversal, secret detection, size limits, analyzer
  across frameworks, Docker detection/generation, restore after disk wipe.
- GitHub: username rules, existence check, OAuth flow (state, encryption, mismatch, replay), repositories,
  branches, repository selection.
- Auth: Google sign-in flow, unverified email rejection, logout, per-user isolation.
- Providers: request/response contract tests for all five providers (mocked HTTP).
- Supabase: startup load, write-back on commit, mirrored deletes, rollback, publishable-key refusal,
  missing-table message, upload restore from Storage.
- Deployment: success only after health check, unreachable → failed, provider failure with log tail,
  not-configured and incompatible blocking, logs endpoint, destroy.

Real provider acceptance: `scripts/acceptance_test.py` deploys the sample projects to each configured
provider, waits for the real deployment, checks the URL and destroys it.
**Record the actual output of this script here for each provider (PASS/FAIL, URL, deployment ID).**

## 23. Results
*To be filled with real observations:* screenshots of each platform's live deployment, the provider
URLs, measured deploy durations and health-check results. Do not include results that were not
actually obtained.

## 24. Limitations
- Depends on each provider's free plan, which can change or be withdrawn.
- Free Render services sleep when idle; first requests are slow.
- Netlify's public API does not expose raw build logs.
- Environment variables are passed to Render and Vercel only in this version.
- SSR frameworks on Cloudflare Pages and Next.js base paths on GitHub Pages need manual adaptation.
- Provider tokens are configured per CloudDeploy Hub instance (operator accounts), not per end user.

## 25. Future Scope
Per-user provider tokens via each provider's OAuth; more free platforms (Fly.io, Koyeb, Railway trial);
custom domains; preview deployments per branch; webhooks instead of polling; cost/usage dashboards
from provider APIs; monorepo multi-service deploys.

## 26. Conclusion
CloudDeploy Hub shows that one framework can drive heterogeneous free cloud platforms through their
native mechanisms while giving users a single, honest workflow: it deploys only where a project can
run and reports success only when the application is actually reachable.
