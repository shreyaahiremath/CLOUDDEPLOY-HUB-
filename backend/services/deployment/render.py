"""Render provider, using the official Render API (https://api-docs.render.com/).

GitHub repository -> Render service (web_service on the free instance type, or static_site)
-> Render builds and deploys -> URL read from the service's serviceDetails.url.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from backend.config import settings
from backend.models import Deployment
from backend.services.deployment.base import (
    PHASE_BUILDING,
    PHASE_DEPLOYING,
    PHASE_FAILED,
    PHASE_LIVE,
    PHASE_QUEUED,
    DeployContext,
    DeployError,
    DeployHandle,
    DeploymentProvider,
    LogLine,
    ProviderStatus,
    slugify,
)
from backend.services.docker import generate_dockerfile
from backend.services.http import DEFAULT_TIMEOUT, ApiError, request

API = "https://api.render.com/v1"

STATUS_MAP = {
    "created": PHASE_QUEUED,
    "queued": PHASE_QUEUED,
    "build_in_progress": PHASE_BUILDING,
    "update_in_progress": PHASE_DEPLOYING,
    "pre_deploy_in_progress": PHASE_DEPLOYING,
    "live": PHASE_LIVE,
    "build_failed": PHASE_FAILED,
    "update_failed": PHASE_FAILED,
    "pre_deploy_failed": PHASE_FAILED,
    "canceled": PHASE_FAILED,
    "deactivated": PHASE_FAILED,
}
NATIVE_RUNTIMES = {"fastapi": "python", "flask": "python", "django": "python", "go": "go", "ruby": "ruby", "rust": "rust"}
SPA_KEYS = {"vite-react", "vite-vue", "vite-svelte", "vite", "create-react-app", "vue", "angular"}


def _fix_for(err: ApiError) -> str | None:
    msg = err.message.lower()
    if err.status == 401:
        return "RENDER_API_KEY is invalid or revoked. Create a new key in Render → Account Settings → API Keys."
    if "repo" in msg or "github" in msg or "repository" in msg:
        return ("Render could not access the repository. For private repos, connect GitHub in the Render dashboard "
                "(Account Settings → Git Providers) and grant access to this repository.")
    if err.status == 402 or "payment" in msg or "free" in msg or "limit" in msg:
        return "Your Render workspace hit a free-plan limit. Delete unused free services or check Render's plan limits."
    if err.status == 409 or "already" in msg:
        return "A service with this name already exists in your Render workspace. Choose another name."
    return None


class RenderProvider(DeploymentProvider):
    key = "render"

    def missing_credentials(self) -> list[str]:
        return [] if settings.render_api_key else ["RENDER_API_KEY"]

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=API, timeout=DEFAULT_TIMEOUT,
            headers={"Authorization": f"Bearer {settings.render_api_key}", "Accept": "application/json"},
        )

    async def _owner_id(self, client: httpx.AsyncClient) -> tuple[str, str]:
        resp = await request(client, "Render", "GET", "/owners", params={"limit": 20})
        owners = [item.get("owner", item) for item in resp.json()]
        if settings.render_owner_id:
            match = next((o for o in owners if o.get("id") == settings.render_owner_id), None)
            if match is None:
                raise DeployError(f"RENDER_OWNER_ID {settings.render_owner_id} is not visible to this API key.")
            return match["id"], match.get("name") or match["id"]
        if not owners:
            raise DeployError("This Render API key has no workspace.")
        return owners[0]["id"], owners[0].get("name") or owners[0]["id"]

    async def check_credentials(self, user_id: int | None = None) -> dict:
        if not self.is_configured():
            return {"ok": False, "account": None, "error": "Provider Not Configured"}
        try:
            async with self._client() as client:
                _, name = await self._owner_id(client)
            return {"ok": True, "account": name, "error": None}
        except (ApiError, DeployError) as exc:
            return {"ok": False, "account": None, "error": str(exc)}

    # ------------------------------------------------------------------------------------------
    def _is_static(self, ctx: DeployContext) -> bool:
        return ctx.analysis.get("app_type") in ("Static Frontend", "Frontend") and ctx.config.build_mode != "docker"

    def _runtime(self, ctx: DeployContext) -> str | None:
        if ctx.config.build_mode == "docker":
            return "docker"
        key = ctx.analysis.get("framework_key")
        if key in NATIVE_RUNTIMES:
            return NATIVE_RUNTIMES[key]
        if ctx.analysis.get("package_manager"):
            return "node"
        return "docker" if ctx.analysis.get("has_dockerfile") else None

    def _commands(self, ctx: DeployContext) -> tuple[str | None, str | None]:
        a = ctx.analysis
        install = ctx.pick("install_command")
        build = ctx.config.build_command or a.get("build_command")
        if self._is_static(ctx):
            parts = [install, build] if build else []
            return (" && ".join(p for p in parts if p) or None), None
        if a.get("language") == "Python":
            build_cmd = install or "pip install -r requirements.txt"
        elif a.get("framework_key") == "go":
            build_cmd = build or "go build -o app ."
        else:
            build_cmd = " && ".join(p for p in (install, build) if p) or "npm install"
        return build_cmd, ctx.pick("start_command")

    def validate(self, ctx: DeployContext) -> tuple[list[str], list[str]]:
        errors, warnings = [], []
        if not ctx.project.repository:
            errors.append("Render deploys from a GitHub repository. Publish this project to GitHub first.")
        runtime = self._runtime(ctx)
        if not self._is_static(ctx):
            if runtime is None:
                errors.append("Could not determine a Render runtime. Add a Dockerfile or choose Docker build mode.")
            elif runtime != "docker" and not ctx.pick("start_command"):
                errors.append("A start command is required for a Render web service.")
        if ctx.config.build_mode == "docker" and not ctx.analysis.get("has_dockerfile"):
            if generate_dockerfile(ctx.analysis) is None:
                errors.append("No Dockerfile found and one could not be generated for this framework.")
            else:
                warnings.append("A generated Dockerfile will be committed to your repository before deploying.")
        for issue in ctx.analysis.get("dockerfile_issues") or []:
            (errors if ctx.config.build_mode == "docker" else warnings).append(issue)
        if ctx.project.repo_private:
            warnings.append("Private repository: Render must have access through its GitHub connection.")
        if not self._is_static(ctx):
            warnings.append("Free web services spin down when idle. The first request after idle may take up to a minute.")
        return errors, warnings

    def preview(self, ctx: DeployContext) -> dict:
        static = self._is_static(ctx)
        build_cmd, start_cmd = self._commands(ctx)
        runtime = "static" if static else self._runtime(ctx)
        dockerfile = None
        if runtime == "docker" and not ctx.analysis.get("has_dockerfile"):
            dockerfile = generate_dockerfile(ctx.analysis)
        return {
            "resource": "Render Static Site" if static else "Render Web Service",
            "plan": "Free" if not static else "Free (static site)",
            "runtime": runtime,
            "build": "Docker" if runtime == "docker" else ("Static build" if static else f"Native ({runtime})"),
            "build_command": build_cmd,
            "start_command": None if static or runtime == "docker" else start_cmd,
            "publish_path": (ctx.pick("output_dir") or ".") if static else None,
            "root_dir": ctx.root_dir or None,
            "region": "oregon",
            "generated_dockerfile": dockerfile,
            "repository_changes": ["Dockerfile"] if dockerfile else [],
        }

    async def deploy(self, ctx: DeployContext) -> DeployHandle:
        self.require_configured()
        project = ctx.project
        branch = ctx.config.branch or project.branch or "main"
        preview = self.preview(ctx)
        async with self._client() as client:
            try:
                if ctx.previous_resource_id:
                    ctx.log(f"Triggering a new deploy on existing Render service {ctx.previous_resource_id}")
                    resp = await request(client, "Render", "POST", f"/services/{ctx.previous_resource_id}/deploys", json={})
                    dep = resp.json()
                    return DeployHandle(dep.get("id"), ctx.previous_resource_id, meta={**ctx.previous_meta})

                owner_id, owner_name = await self._owner_id(client)
                ctx.log(f"Using Render workspace '{owner_name}'")
                if preview["generated_dockerfile"]:
                    ctx.log("Committing generated Dockerfile to the repository")
                    await ctx.github.put_file(
                        project.github_owner, project.github_repo,
                        f"{ctx.root_dir}/Dockerfile".lstrip("/"), preview["generated_dockerfile"],
                        "Add Dockerfile generated by CloudDeploy Hub", branch,
                    )
                name = slugify(ctx.config.name or project.name)
                body: dict = {
                    "name": name,
                    "ownerId": owner_id,
                    "repo": f"https://github.com/{project.repository}",
                    "branch": branch,
                    "autoDeployTrigger": "off",
                }
                if ctx.root_dir:
                    body["rootDir"] = ctx.root_dir
                if ctx.config.env_vars:
                    body["envVars"] = [{"key": k, "value": v} for k, v in ctx.config.env_vars.items()]
                if preview["runtime"] == "static":
                    body["type"] = "static_site"
                    details: dict = {
                        "publishPath": preview["publish_path"],
                        "buildCommand": preview["build_command"] or 'echo "No build step"',
                    }
                    if ctx.analysis.get("framework_key") in SPA_KEYS:
                        details["routes"] = [{"type": "rewrite", "source": "/*", "destination": "/index.html"}]
                    body["serviceDetails"] = details
                else:
                    body["type"] = "web_service"
                    runtime = preview["runtime"]
                    if runtime == "docker":
                        env_details = {"dockerfilePath": "./Dockerfile", "dockerContext": "."}
                    else:
                        env_details = {"buildCommand": preview["build_command"], "startCommand": preview["start_command"]}
                    details = {"runtime": runtime, "plan": "free", "region": "oregon", "envSpecificDetails": env_details}
                    if ctx.config.health_check_path:
                        details["healthCheckPath"] = ctx.config.health_check_path
                    body["serviceDetails"] = details
                ctx.log(f"Creating Render {body['type']} '{name}' from {project.repository}@{branch}")
                resp = await request(client, "Render", "POST", "/services", json=body)
            except ApiError as exc:
                raise DeployError(f"Render rejected the request: {exc.message}", _fix_for(exc)) from exc

            data = resp.json()
            service = data.get("service", data)
            service_id = service["id"]
            deploy_id = data.get("deployId")
            url = (service.get("serviceDetails") or {}).get("url")
            ctx.log(f"Render service created: {service_id}")
            if not deploy_id:
                deploy_id = await self._latest_deploy_id(client, service_id)
            return DeployHandle(deploy_id, service_id, url, meta={"owner_id": owner_id, "service_type": body["type"]})

    async def _latest_deploy_id(self, client: httpx.AsyncClient, service_id: str) -> str | None:
        resp = await request(client, "Render", "GET", f"/services/{service_id}/deploys", params={"limit": 1})
        items = resp.json()
        if items:
            return items[0].get("deploy", items[0]).get("id")
        return None

    async def get_status(self, deployment: Deployment) -> ProviderStatus:
        sid = deployment.provider_resource_id
        async with self._client() as client:
            did = deployment.deployment_id or await self._latest_deploy_id(client, sid)
            if not did:
                return ProviderStatus(PHASE_QUEUED, "waiting_for_deploy")
            resp = await request(client, "Render", "GET", f"/services/{sid}/deploys/{did}")
        dep = resp.json()
        dep = dep.get("deploy", dep)
        raw = dep.get("status", "unknown")
        phase = STATUS_MAP.get(raw, PHASE_BUILDING)
        error = None
        if phase == PHASE_FAILED:
            error = f"Render deploy ended with status '{raw}'"
        return ProviderStatus(phase, raw, error=error, deployment_id=did)

    async def get_logs(self, deployment: Deployment) -> list[LogLine]:
        owner_id = deployment.meta.get("owner_id")
        if not owner_id or not deployment.provider_resource_id:
            return []
        params: list[tuple[str, str]] = [
            ("ownerId", owner_id), ("resource", deployment.provider_resource_id),
            ("limit", "100"), ("direction", "backward"),
            ("startTime", deployment.created_at.isoformat()),
        ]
        async with self._client() as client:
            resp = await request(client, "Render", "GET", "/logs", params=params)
        lines = []
        for item in resp.json().get("logs", []):
            labels = {lab.get("name"): lab.get("value") for lab in item.get("labels", [])}
            level = "error" if labels.get("level") == "error" else "info"
            lines.append(LogLine(_parse_ts(item.get("timestamp")), item.get("message", ""), f"render:{labels.get('type', 'log')}", level))
        return sorted(lines, key=lambda line: str(line.ts))

    async def get_outputs(self, deployment: Deployment) -> dict:
        async with self._client() as client:
            resp = await request(client, "Render", "GET", f"/services/{deployment.provider_resource_id}")
        service = resp.json()
        return {
            "public_url": (service.get("serviceDetails") or {}).get("url"),
            "dashboard_url": service.get("dashboardUrl"),
            "service_id": service.get("id"),
        }

    async def destroy(self, deployment: Deployment) -> None:
        if not deployment.provider_resource_id:
            return
        async with self._client() as client:
            await request(client, "Render", "DELETE", f"/services/{deployment.provider_resource_id}", ok=(404,))


def _parse_ts(value: str | None) -> datetime | str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
