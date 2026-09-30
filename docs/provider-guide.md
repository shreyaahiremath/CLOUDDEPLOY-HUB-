# Provider Guide

Each section covers what the free option runs, the credentials the backend needs, exactly what
CloudDeploy Hub does, and where the URL, status and logs come from.

## Render

- **Runs:** FastAPI / Flask / Django, Node/Express, Go, Ruby, Rust, any Dockerfile (free web
  service); static and SPA builds (free static site).
- **Credentials:** `RENDER_API_KEY` (optional `RENDER_OWNER_ID`).
- **Source:** a GitHub repository. Private repos need Render's own GitHub connection.
- **Deploy:** `POST /v1/services` with `type`, `ownerId`, `repo`, `branch`, `rootDir`, `envVars` and
  `serviceDetails` (`runtime`, `plan: "free"`, build/start commands or Docker settings). SPA static
  sites get a `/* → /index.html` rewrite.
- **Status:** `GET /v1/services/{id}/deploys/{deployId}`: `build_in_progress` → `update_in_progress` →
  `live` (or `build_failed` / `update_failed` / `canceled`).
- **Logs:** `GET /v1/logs?ownerId=…&resource=…`. **URL:** `serviceDetails.url`.
- **Destroy:** `DELETE /v1/services/{id}`.
- **Free-plan notes:** services spin down when idle (first request is slow); monthly usage caps apply.

## Vercel

- **Runs:** Next.js, React/Vite, Vue, Svelte, Astro, static sites, serverless functions. Python/Express
  backends only as serverless functions (shown as *needs adaptation*).
- **Credentials:** `VERCEL_TOKEN` (optional `VERCEL_TEAM_ID`).
- **Source:** uploaded files or a GitHub repository. No Vercel GitHub app install is needed, because
  files are uploaded through the API.
- **Deploy:** `POST /v2/files` per file (header `x-vercel-digest: <sha1>`) → `POST /v11/projects` →
  optional `POST /v10/projects/{id}/env` → `POST /v13/deployments` with `target: "production"`.
- **Status:** `readyState` (`QUEUED` → `BUILDING` → `READY` / `ERROR`). **Logs:** `/v3/deployments/{id}/events`.
- **URL:** the production alias (`<project>.vercel.app`) from the deployment's `alias` list.
- **Destroy:** `DELETE /v9/projects/{id}`.

## Netlify

- **Runs:** static sites, SPA builds, Next.js/Nuxt through Netlify's runtime, Netlify Functions.
- **Credentials:** `NETLIFY_AUTH_TOKEN`.
- **Source:** uploaded files or a GitHub repository (downloaded as a tarball through the GitHub API).
- **Deploy:** `POST /api/v1/sites` → `POST /api/v1/sites/{id}/builds` (multipart `title` + `zip`). Netlify
  builds the zip. If the project has no `netlify.toml`, one is generated (build command, publish dir,
  `NODE_VERSION=20`, SPA redirect) and shown in the preview.
- **Status:** `GET /api/v1/deploys/{deploy_id}` `state` (`building` → `processing` → `ready` / `error`).
- **Logs:** Netlify's public API does not expose raw build logs; CloudDeploy Hub shows the deploy
  state, summary messages and error message, plus a link to the full log in Netlify.
- **URL:** site `ssl_url`. **Destroy:** `DELETE /api/v1/sites/{id}`.

## GitHub Pages

- **Runs:** static sites only. Free for public repositories on GitHub Free.
- **Credentials:** the user's GitHub connection (scopes `repo`, `workflow`).
- **Deploy:** `POST /repos/{o}/{r}/pages {"build_type": "workflow"}` → commit
  `.github/workflows/clouddeploy-pages.yml` → `workflow_dispatch`.
  Vite builds get `--base=/<repo>/`; CRA gets `PUBLIC_URL=/<repo>`; SPAs get a `404.html` fallback.
- **Status/Logs:** the Actions run and its job logs. **URL:** `GET /repos/{o}/{r}/pages` → `html_url`.
- **Destroy:** `DELETE /repos/{o}/{r}/pages` (the workflow file stays in the repository).

## Cloudflare Pages

- **Runs:** static sites, SPA builds, Pages Functions. Not long-running servers or unadapted SSR.
- **Credentials:** `CLOUDFLARE_API_TOKEN` (Cloudflare Pages: Edit), `CLOUDFLARE_ACCOUNT_ID`, and the
  user's GitHub connection.
- **Deploy:** `POST /accounts/{id}/pages/projects {name, production_branch}` → store two encrypted
  Actions secrets (libsodium sealed box) → commit `.github/workflows/clouddeploy-cloudflare.yml` →
  `workflow_dispatch`. The workflow builds and runs `npx wrangler@4 pages deploy`.
- **Status:** Actions run, then the latest Cloudflare deployment's `latest_stage`.
- **Logs:** Actions job logs, plus Cloudflare deployment history logs where available.
- **URL:** `https://<project subdomain>.pages.dev`. **Destroy:** `DELETE /accounts/{id}/pages/projects/{name}`.

## Adding another provider

1. Add a `ProviderCapability` entry and compatibility rules in `capabilities.py`.
2. Implement `DeploymentProvider` in a new module (validate, preview, deploy, get_status, get_logs,
   get_outputs, destroy) using the provider's official API.
3. Register it in `services/deployment/__init__.py` and add contract tests.
4. Run `scripts/acceptance_test.py` against a real account before calling it supported.
