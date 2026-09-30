# Git2Live

**Unified Multi-Cloud Application Deployment Framework** (college Minor Project)

Git2Live takes **your own application** (a GitHub repository or an uploaded project folder),
analyzes it, shows which **free** cloud platforms can actually run it, deploys it through each
provider's official API, and returns the **real public URL** only after that URL passes a health check.

```text
MY PROJECT → Git2Live → GitHub / Upload → Analyze → Select FREE PLATFORM
→ Real Provider API → Real Build → Real Deployment → Real Public URL → Health Check → LIVE
```

There are no simulated deployments, fake URLs, fake logs, fake repositories or fake statuses.
If a provider has no credentials, the app says **Provider Not Configured**. It never reports success.

## Supported free platforms

| Platform | Free option | Deploys | How Git2Live deploys |
|---|---|---|---|
| Render | Free web service / static site | FastAPI, Flask, Django, Node, Docker, static | Render API: creates a service from your GitHub repo |
| Vercel | Hobby | React/Vite, Next.js, static, serverless | Vercel API: uploads files and creates a production deployment |
| Netlify | Free | React/Vite, static, Next.js, functions | Netlify Build API: uploads a source zip that Netlify builds |
| GitHub Pages | Free for public repos | Static sites | GitHub Actions workflow + `actions/deploy-pages` |
| Cloudflare Pages | Free | Static sites, Pages Functions | GitHub Actions + Cloudflare's official `wrangler pages deploy` |

> Free plan available subject to the provider's current limits and terms. Free plans are not
> unlimited, may sleep or spin down, and can change at any time.

No AWS, Azure, GCP, Oracle Cloud or other paid/credit-based infrastructure is included.

## Features

- **Continue with Google** sign-in; every project, GitHub connection and deployment is private to its owner.
- **GitHub integration**: username field (identity only) + real OAuth, repository and branch browser,
  username-mismatch warning, encrypted token storage, token revocation on disconnect.
- **Local upload**: folder drag-and-drop or `.zip`, with validation for path traversal, size limits,
  `.env` files, keys and secrets, and executables. Uploads are stored in Supabase Storage so they survive restarts.
- **Local project → GitHub**: review the exact file list, choose private/public, auto `.gitignore`.
- **Project Analyzer**: language, framework, build files, app type, commands, Dockerfile validation.
- **Compatibility engine**: compatible / needs adaptation / not compatible, per platform, with reasons.
- **Dockerfile generation** (shown before use) for Docker deploys on Render.
- **Deployment preview**, **live status** from provider APIs, **real provider logs**, **health checks**,
  **history**, **redeploy / try again**, **destroy**.

## Tech stack

| Layer | Technology | Hosted on |
|---|---|---|
| Frontend | React 19, Vite, TypeScript, React Router | Vercel |
| Backend | FastAPI, SQLAlchemy 2.0, Pydantic, httpx | Render |
| Database | Supabase, through its HTTPS API + Storage (SQLite working copy; SQLite only for local development) | Supabase |
| Auth | Google OpenID Connect (users), GitHub OAuth (repositories) | |

## Repository layout

```text
backend/            FastAPI app (api/, models/, schemas/, services/, workers/, database/, main.py)
  services/deployment/  base.py render.py vercel.py netlify.py github_pages.py cloudflare.py
  tests/            pytest suite (54 tests)
frontend/           React + Vite + TypeScript app (vercel.json included)
docs/               architecture, guides, FAQs, report content
samples/            sample-project (static) and sample-fastapi, for integration testing only
scripts/            acceptance_test.py: real end-to-end provider test
render.yaml         Render Blueprint for the backend
```

## Run locally

```bash
# backend (from the repository root)
python -m venv backend/.venv
backend/.venv/Scripts/pip install -r backend/requirements-dev.txt   # macOS/Linux: backend/.venv/bin/pip
cp backend/.env.example backend/.env        # set DEV_LOGIN=1 to sign in without Google locally
backend/.venv/Scripts/python -m uvicorn backend.main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api to :8000)
```

Run the tests: `backend/.venv/Scripts/python -m pytest backend/tests -q`

## Deploy Git2Live itself

See [docs/deployment-guide.md](docs/deployment-guide.md): **Supabase** (database) → **Render**
(backend, via `render.yaml`) → **Vercel** (frontend, root directory `frontend`) → Google and GitHub
OAuth redirect URLs.

## Verifying providers for real

A provider is not "working" just because its code exists. Run
`scripts/acceptance_test.py` with real credentials: it deploys the sample projects, waits for the
provider, opens the returned URL, and destroys the resource. The Providers page also marks a platform
**End-to-end verified** only after a real deployment on it reached SUCCESS with a healthy URL.

## Documentation

[Architecture](docs/architecture.md) · [Deployment guide](docs/deployment-guide.md) ·
[GitHub integration](docs/github-integration.md) · [Provider guide](docs/provider-guide.md) ·
[Troubleshooting](docs/troubleshooting.md) · [FAQs](docs/faqs.md) ·
[Project report content](docs/project-report-content.md)

## Trademarks

Render, Vercel, Netlify, GitHub and Cloudflare names and logos are trademarks of their respective
owners. They appear only to identify the platforms Git2Live can deploy to. Git2Live is an independent
student project and is not affiliated with or endorsed by them. Logo path data comes from
[Simple Icons](https://simpleicons.org) (CC0-1.0).
