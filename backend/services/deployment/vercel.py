"""Vercel provider, using the official Vercel REST API (https://vercel.com/docs/rest-api).

Source files -> POST /v2/files (content-addressed upload) -> POST /v11/projects -> POST /v13/deployments
(target=production) -> Vercel builds -> production alias read from the deployment.
Works for both uploaded projects and GitHub repositories, and needs no Vercel GitHub app install.
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone

import httpx

from backend.config import settings
from backend.models import Deployment
from backend.services.deployment.base import (
    PHASE_BUILDING,
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
    unique_slug,
)
from backend.services.deployment.source import snapshot
from backend.services.http import DEFAULT_TIMEOUT, ApiError, request

API = "https://api.vercel.com"

FRAMEWORK_SLUGS = {
    "nextjs": "nextjs", "vite-react": "vite", "vite-vue": "vite", "vite-svelte": "vite", "vite": "vite",
    "create-react-app": "create-react-app", "vue": "vue", "angular": "angular", "astro": "astro",
    "sveltekit": "sveltekit-1", "nuxt": "nuxtjs",
}
STATE_MAP = {
    "QUEUED": PHASE_QUEUED, "INITIALIZING": PHASE_QUEUED, "BUILDING": PHASE_BUILDING,
    "READY": PHASE_LIVE, "ERROR": PHASE_FAILED, "CANCELED": PHASE_FAILED,
}
BACKEND_TYPES = {"Backend API"}


def _fix_for(err: ApiError) -> str | None:
    msg = err.message.lower()
    if err.status == 401 or (err.status == 403 and "token" in msg):
        return "VERCEL_TOKEN is invalid or expired. Create a new token at vercel.com/account/tokens."
    if err.status == 403:
        return "The token cannot access this scope. If the project belongs to a team, set VERCEL_TEAM_ID."
    if err.status == 402 or "limit" in msg:
        return "Your Vercel Hobby account hit a usage limit. Check the Usage tab in the Vercel dashboard."
    if "framework" in msg:
        return "Vercel detected a different framework. Set the framework-specific build command and output directory manually."
    return None


class VercelProvider(DeploymentProvider):
    key = "vercel"

    def missing_credentials(self) -> list[str]:
        return [] if settings.vercel_token else ["VERCEL_TOKEN"]

    def _client(self) -> httpx.AsyncClient:
        params = {"teamId": settings.vercel_team_id} if settings.vercel_team_id else {}
        return httpx.AsyncClient(
            base_url=API, timeout=DEFAULT_TIMEOUT, params=params,
            headers={"Authorization": f"Bearer {settings.vercel_token}"},
        )

    async def check_credentials(self, user_id: int | None = None) -> dict:
        if not self.is_configured():
            return {"ok": False, "account": None, "error": "Provider Not Configured"}
        try:
            async with self._client() as client:
                user = (await request(client, "Vercel", "GET", "/v2/user")).json().get("user", {})
            return {"ok": True, "account": user.get("username") or user.get("email"), "error": None}
        except ApiError as exc:
            return {"ok": False, "account": None, "error": str(exc)}

    def _settings(self, ctx: DeployContext) -> dict:
        a = ctx.analysis
        key = a.get("framework_key")
        project_settings: dict = {}
        if a.get("app_type") not in BACKEND_TYPES:
            project_settings["framework"] = FRAMEWORK_SLUGS.get(key)
        if ctx.config.install_command:
            project_settings["installCommand"] = ctx.config.install_command
        if ctx.config.build_command:
            project_settings["buildCommand"] = ctx.config.build_command
        if ctx.config.output_dir:
            project_settings["outputDirectory"] = ctx.config.output_dir
        elif key == "static" and a.get("output_dir") not in (None, "."):
            project_settings["outputDirectory"] = a["output_dir"]
        return project_settings

    def validate(self, ctx: DeployContext) -> tuple[list[str], list[str]]:
        errors, warnings = [], []
        if ctx.project.source_type != "upload" and not ctx.project.repository:
            errors.append("Project has no source files.")
        if ctx.analysis.get("app_type") in BACKEND_TYPES:
            warnings.append("Backend code runs as Vercel serverless functions: no persistent process or background tasks.")
        if ctx.config.health_check_path:
            warnings.append(f"Health check will call {ctx.config.health_check_path} on the production URL.")
        return errors, warnings

    def preview(self, ctx: DeployContext) -> dict:
        s = self._settings(ctx)
        return {
            "resource": "Vercel Project + Production Deployment",
            "plan": "Hobby (free)",
            "build": "Vercel build (" + (s.get("framework") or "auto-detect") + ")",
            "framework": s.get("framework"),
            "install_command": s.get("installCommand") or "Vercel default",
            "build_command": s.get("buildCommand") or ctx.analysis.get("build_command") or "Vercel default",
            "output_dir": s.get("outputDirectory") or ctx.analysis.get("output_dir") or "Vercel default",
            "root_dir": ctx.root_dir or None,
            "upload": "Source files are uploaded to Vercel (validated: no .env, secrets or executables).",
            "repository_changes": [],
        }

    async def deploy(self, ctx: DeployContext) -> DeployHandle:
        self.require_configured()
        files = await snapshot(ctx)
        project_settings = self._settings(ctx)
        async with self._client() as client:
            try:
                project_id = ctx.previous_resource_id
                project_name = ctx.previous_meta.get("project_name")
                if not project_id:
                    project_id, project_name = await self._create_project(client, ctx, project_settings.get("framework"))
                    ctx.log(f"Created Vercel project '{project_name}' ({project_id})")
                for key, value in ctx.config.env_vars.items():
                    await request(
                        client, "Vercel", "POST", f"/v10/projects/{project_id}/env", params={"upsert": "true"},
                        json={"key": key, "value": value, "type": "encrypted", "target": ["production", "preview"]},
                    )
                if ctx.config.env_vars:
                    ctx.log(f"Set {len(ctx.config.env_vars)} environment variable(s) on the Vercel project")

                ctx.log(f"Uploading {len(files)} file(s) to Vercel")
                manifest = await self._upload(client, files)
                body = {
                    "name": project_name,
                    "project": project_id,
                    "target": "production",
                    "files": manifest,
                    "projectSettings": project_settings,
                }
                resp = await request(
                    client, "Vercel", "POST", "/v13/deployments",
                    params={"skipAutoDetectionConfirmation": "1", "forceNew": "1"}, json=body,
                )
            except ApiError as exc:
                raise DeployError(f"Vercel rejected the request: {exc.message}", _fix_for(exc)) from exc
        dep = resp.json()
        ctx.log(f"Vercel deployment created: {dep['id']}")
        return DeployHandle(dep["id"], project_id, meta={"project_name": project_name, "deployment_host": dep.get("url")})

    async def _create_project(self, client: httpx.AsyncClient, ctx: DeployContext, framework: str | None) -> tuple[str, str]:
        base = ctx.config.name or ctx.project.name
        for name in (slugify(base, 90), unique_slug(base, 90), unique_slug(base, 90)):
            body: dict = {"name": name}
            if framework:
                body["framework"] = framework
            try:
                data = (await request(client, "Vercel", "POST", "/v11/projects", json=body)).json()
                return data["id"], data["name"]
            except ApiError as exc:
                if exc.status != 409:
                    raise
        raise DeployError("Could not find a free Vercel project name.", "Choose a different deployment name.")

    async def _upload(self, client: httpx.AsyncClient, files: dict[str, bytes]) -> list[dict]:
        sem = asyncio.Semaphore(8)

        async def one(path: str, data: bytes) -> dict:
            sha = hashlib.sha1(data).hexdigest()
            async with sem:
                await request(
                    client, "Vercel", "POST", "/v2/files", content=data,
                    headers={"Content-Type": "application/octet-stream", "x-vercel-digest": sha},
                )
            return {"file": path, "sha": sha, "size": len(data)}

        return list(await asyncio.gather(*(one(p, d) for p, d in files.items())))

    async def _deployment(self, deployment_id: str) -> dict:
        async with self._client() as client:
            return (await request(client, "Vercel", "GET", f"/v13/deployments/{deployment_id}")).json()

    async def get_status(self, deployment: Deployment) -> ProviderStatus:
        dep = await self._deployment(deployment.deployment_id)
        raw = dep.get("readyState") or dep.get("status") or "UNKNOWN"
        phase = STATE_MAP.get(raw, PHASE_BUILDING)
        error = None
        if phase == PHASE_FAILED:
            error = dep.get("errorMessage") or f"Vercel deployment ended with state {raw}"
        return ProviderStatus(phase, raw, error=error)

    async def get_outputs(self, deployment: Deployment) -> dict:
        dep = await self._deployment(deployment.deployment_id)
        aliases = [a for a in dep.get("alias") or [] if a]
        project_name = deployment.meta.get("project_name")
        preferred = next((a for a in aliases if a == f"{project_name}.vercel.app"), None)
        if preferred is None and aliases:
            preferred = min(aliases, key=len)
        host = preferred or dep.get("url")
        return {
            "public_url": f"https://{host}" if host else None,
            "deployment_url": f"https://{dep['url']}" if dep.get("url") else None,
            "inspector_url": dep.get("inspectorUrl"),
        }

    async def get_logs(self, deployment: Deployment) -> list[LogLine]:
        if not deployment.deployment_id:
            return []
        async with self._client() as client:
            resp = await request(
                client, "Vercel", "GET", f"/v3/deployments/{deployment.deployment_id}/events",
                params={"builds": "1", "direction": "forward", "limit": "1000"},
            )
        events = resp.json()
        if isinstance(events, dict):
            events = events.get("events", [])
        lines = []
        for ev in events:
            payload = ev.get("payload") or {}
            text = payload.get("text") or ev.get("text")
            if not text or ev.get("type") == "delimiter":
                continue
            created = ev.get("created") or payload.get("date")
            ts = datetime.fromtimestamp(created / 1000, tz=timezone.utc) if isinstance(created, (int, float)) else None
            level = "error" if ev.get("type") == "stderr" or payload.get("info", {}).get("type") == "error" else "info"
            lines.append(LogLine(ts, text.rstrip(), "vercel:build", level))
        return lines

    async def destroy(self, deployment: Deployment) -> None:
        if not deployment.provider_resource_id:
            return
        async with self._client() as client:
            await request(client, "Vercel", "DELETE", f"/v9/projects/{deployment.provider_resource_id}", ok=(404,))
