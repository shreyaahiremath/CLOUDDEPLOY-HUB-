# Architecture

```text
                    Git2Live
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
        Real URL                      Real URL
```

## System components

| Component | Location | Responsibility |
|---|---|---|
| Web UI | `frontend/` (Vercel) | All pages; talks to the API with a bearer session token |
| API | `backend/api/` (Render) | REST endpoints: auth, GitHub, projects, deployments, providers, docs |
| Auth | `backend/services/auth.py` | Google OpenID Connect code flow; hashed server-side sessions |
| GitHub service | `backend/services/github/` | OAuth, repos, branches, trees, publish via Git Data API, Actions, Pages |
| Workspace | `backend/services/workspace/` | Upload validation, zip handling, DB-backed workspace restore |
| Project Analyzer | `backend/services/project_analyzer/` | Static manifest analysis (no code execution) |
| Docker service | `backend/services/docker/` | Dockerfile validation and generation |
| Providers | `backend/services/deployment/` | `DeploymentProvider` implementations + capability catalog |
| Worker | `backend/workers/deployment_worker.py` | Async orchestration: submit → poll → health check → record |
| Database | Supabase (HTTPS API + Storage), SQLite working copy | Users, sessions, projects, deployments, events, connections; upload zips in Storage |
| Supabase sync | `backend/services/supabase_store.py` | Loads all tables at startup; mirrors every committed insert/update/delete back to Supabase |

## Provider abstraction

```python
class DeploymentProvider(ABC):
    def validate(self, ctx) -> (errors, warnings)   # no side effects
    def preview(self, ctx) -> dict                  # exactly what will be created/changed
    async def deploy(self, ctx) -> DeployHandle     # real provider call
    async def get_status(self, deployment) -> ProviderStatus
    async def get_logs(self, deployment) -> list[LogLine]
    async def get_outputs(self, deployment) -> dict # public_url from the provider
    async def destroy(self, deployment) -> None
```

Each provider uses its own mechanism. They do not share one "infrastructure" technique:

| Provider | Mechanism |
|---|---|
| Render | `POST /v1/services` (repo URL, `plan: free`, native runtime or Docker) → deploy status → `serviceDetails.url` |
| Vercel | `POST /v2/files` (SHA-1 addressed) → `POST /v11/projects` → `POST /v13/deployments` `target=production` → alias |
| Netlify | `POST /api/v1/sites` → `POST /sites/{id}/builds` (multipart source zip) → `GET /deploys/{id}` → `ssl_url` |
| GitHub Pages | `POST /repos/{o}/{r}/pages {build_type: workflow}` → commit workflow → `workflow_dispatch` → `GET /pages` |
| Cloudflare Pages | `POST /accounts/{id}/pages/projects` → Actions secrets (sealed box) → workflow runs `wrangler pages deploy` |

## Deployment lifecycle

```text
QUEUED → VALIDATING → (QUEUED) → BUILDING → DEPLOYING → HEALTH_CHECKING → SUCCESS
                                                     ↘ FAILED (provider error / unreachable URL)
SUCCESS | FAILED → DESTROYING → DESTROYED
```

- Every status comes from a provider response; nothing advances on a timer.
- `SUCCESS` requires the provider-returned URL to answer HTTP 2xx (`/health` then `/` for APIs).
- A provider becomes **End-to-end verified** only when one of its deployments reaches `SUCCESS`.
- On restart, in-flight deployments are resumed from the database.

## Data model

`users`, `auth_sessions` (token SHA-256 only), `github_connections` (Fernet-encrypted token),
`oauth_states`, `projects`, `project_sources` (upload zip), `deployments` (id, project_name,
github_username, repository, branch, provider, deployment_id, provider_resource_id, status,
public_url, created_at, updated_at, error_message, …), `deployment_events`, `provider_verifications`.

## Security model

- Provider tokens exist only in backend environment variables; the browser only sees "set / not set".
- GitHub OAuth tokens and deployment environment-variable values are encrypted at rest (`SECRET_KEY`).
- Session tokens are random 256-bit values; only their hash is stored; they travel in a URL fragment
  once, then as an `Authorization` header.
- Uploaded code is never executed by Git2Live; builds run on the provider or in the user's
  own GitHub Actions.
- Every query is scoped to the signed-in user.
- Supabase tables have Row Level Security enabled with no public policies; only the backend's secret key can read or write them.
