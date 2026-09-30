"""Background orchestration of deployments.

All status transitions come from real provider responses. Status is never advanced on a timer, and
SUCCESS is only recorded after the provider's own public URL passes an HTTP health check.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from backend.config import settings
from backend.database import SessionLocal
from backend.models import Deployment, DeploymentEvent, DeploymentStatus as S, Project, ProviderVerification
from backend.services.deployment import get_provider
from backend.services.deployment.base import (
    PHASE_BUILDING,
    PHASE_DEPLOYING,
    PHASE_FAILED,
    PHASE_LIVE,
    PHASE_QUEUED,
    DeployConfig,
    DeployContext,
    DeployError,
    ProviderNotConfigured,
)
from backend.services.deployment.health import check_with_retries, paths_for
from backend.services.github import client_for, get_connection
from backend.services.http import ApiError
from backend.services.security import open_env

log = logging.getLogger("clouddeploy.worker")
_tasks: dict[int, asyncio.Task] = {}

PHASE_TO_STATUS = {
    PHASE_QUEUED: S.QUEUED, PHASE_BUILDING: S.BUILDING, PHASE_DEPLOYING: S.DEPLOYING,
}


def _event(db, dep: Deployment, message: str, level: str = "info") -> None:
    db.add(DeploymentEvent(deployment_id=dep.id, message=message, level=level))
    db.commit()


def _fail(db, dep: Deployment, reason: str, fix: str | None = None) -> None:
    dep.status = S.FAILED
    dep.error_message = reason
    dep.suggested_fix = fix
    dep.finished_at = datetime.now(timezone.utc)
    db.commit()
    _event(db, dep, f"Deployment failed: {reason}", "error")


def start(deployment_id: int) -> None:
    _spawn(deployment_id, run_deployment(deployment_id))


def start_destroy(deployment_id: int) -> None:
    _spawn(deployment_id, run_destroy(deployment_id))


def _spawn(deployment_id: int, coro) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _tasks[deployment_id] = task
    task.add_done_callback(lambda _t: _tasks.pop(deployment_id, None))


def resume_active() -> None:
    """After a restart, continue watching deployments that were mid-flight."""
    with SessionLocal() as db:
        rows = db.query(Deployment).filter(Deployment.status.in_(list(S.ACTIVE))).all()
        for dep in rows:
            if dep.status == S.DESTROYING:
                start_destroy(dep.id)
            elif dep.provider_resource_id or dep.deployment_id:
                _spawn(dep.id, watch(dep.id))
            else:
                _fail(db, dep, "Git2Live restarted before the deployment was submitted to the provider.",
                      "Click Try Again to submit it again.")


async def run_deployment(deployment_id: int) -> None:
    with SessionLocal() as db:
        dep = db.get(Deployment, deployment_id)
        project = db.get(Project, dep.project_id)
        provider = get_provider(dep.provider)
        conn = get_connection(db, dep.user_id)
        previous = None
        if dep.meta.get("reuse_from"):
            previous = db.get(Deployment, dep.meta["reuse_from"])

        dep.status = S.VALIDATING
        db.commit()
        _event(db, dep, f"Validating deployment to {provider.name}")
        try:
            async with client_for(db, dep.user_id) as gh:
                ctx = DeployContext(
                    project=project,
                    analysis=project.analysis or {},
                    config=DeployConfig.from_dict(open_env(dep.config)),
                    github=gh,
                    github_login=conn.verified_login if conn else None,
                    log=lambda msg: _event(db, dep, msg),
                    previous_resource_id=previous.provider_resource_id if previous and previous.status != S.DESTROYED else None,
                    previous_meta=previous.meta if previous and previous.status != S.DESTROYED else {},
                )
                provider.require_configured()
                errors, _warnings = provider.validate(ctx)
                if errors:
                    _fail(db, dep, " ".join(errors), "Fix the issues above and try again.")
                    return
                dep.status = S.QUEUED
                db.commit()
                handle = await provider.deploy(ctx)
        except ProviderNotConfigured as exc:
            _fail(db, dep, f"Provider Not Configured: missing {', '.join(exc.missing)}",
                  "Add the missing values to backend/.env and restart the backend.")
            return
        except DeployError as exc:
            _fail(db, dep, exc.reason, exc.suggested_fix)
            return
        except ApiError as exc:
            _fail(db, dep, f"{exc.service} API error: {exc.message}")
            return
        except FileNotFoundError as exc:
            _fail(db, dep, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - surface unexpected errors instead of hanging
            log.exception("deploy crashed")
            _fail(db, dep, f"Unexpected error while submitting the deployment: {exc}")
            return

        dep.deployment_id = handle.deployment_id
        dep.provider_resource_id = handle.resource_id
        if handle.public_url:
            dep.public_url = handle.public_url
        dep.set_meta(**handle.meta)
        db.commit()
        _event(db, dep, f"Submitted to {provider.name}" + (f" (deployment {handle.deployment_id})" if handle.deployment_id else ""))
    await watch(deployment_id)


async def watch(deployment_id: int) -> None:
    started = time.monotonic()
    last_raw = None
    while True:
        with SessionLocal() as db:
            dep = db.get(Deployment, deployment_id)
            if dep is None or dep.status in S.TERMINAL or dep.status == S.DESTROYING:
                return
            provider = get_provider(dep.provider)
            if time.monotonic() - started > settings.deployment_timeout_seconds:
                _fail(db, dep, f"Timed out after {settings.deployment_timeout_seconds // 60} minutes waiting for {provider.name}.",
                      "Open the provider dashboard to check the build, then try again.")
                return
            try:
                st = await provider.get_status(dep)
            except ApiError as exc:
                _event(db, dep, f"Could not read status from {provider.name}: {exc.message}", "warn")
                await asyncio.sleep(settings.poll_interval_seconds * 2)
                continue
            if st.meta:
                dep.set_meta(**st.meta)
            if st.deployment_id and st.deployment_id != dep.deployment_id:
                dep.deployment_id = st.deployment_id
            dep.provider_status = st.raw
            if st.raw != last_raw:
                _event(db, dep, f"{provider.name} status: {st.raw}")
                last_raw = st.raw

            if st.phase == PHASE_FAILED:
                reason = st.error or f"{provider.name} reported a failure"
                tail = await _error_tail(provider, dep)
                if tail:
                    reason = f"{reason}. Last log lines:\n{tail}"
                _fail(db, dep, reason, "Open the logs to see the provider's build output, fix the error, then try again.")
                return
            if st.phase == PHASE_LIVE:
                dep.status = S.HEALTH_CHECKING
                db.commit()
                await _health_check(db, dep, provider)
                return
            dep.status = PHASE_TO_STATUS.get(st.phase, S.BUILDING)
            db.commit()
        await asyncio.sleep(settings.poll_interval_seconds)


async def _error_tail(provider, dep: Deployment) -> str | None:
    try:
        lines = await provider.get_logs(dep)
    except Exception:  # noqa: BLE001 - logs are best effort here
        return None
    errors = [ln.message for ln in lines if ln.level == "error"] or [ln.message for ln in lines]
    return "\n".join(errors[-8:]) if errors else None


async def _health_check(db, dep: Deployment, provider) -> None:
    try:
        outputs = await provider.get_outputs(dep)
    except ApiError as exc:
        _fail(db, dep, f"Deployed, but could not read the public URL from {provider.name}: {exc.message}")
        return
    url = outputs.get("public_url") or dep.public_url
    dep.set_meta(outputs=outputs)
    if not url:
        _fail(db, dep, f"{provider.name} did not return a public URL.")
        return
    dep.public_url = url
    db.commit()
    project = db.get(Project, dep.project_id)
    paths = paths_for((project.analysis or {}).get("app_type"), dep.config.get("health_check_path"))
    _event(db, dep, f"Health check: GET {url} ({', '.join(paths)})")
    result = await check_with_retries(url, paths)
    dep.health_detail = result.detail
    dep.finished_at = datetime.now(timezone.utc)
    if result.healthy:
        dep.health_status = "healthy"
        dep.status = S.SUCCESS
        dep.error_message = None
        db.merge(ProviderVerification(provider=dep.provider, deployment_id=dep.id, public_url=url,
                                      verified_at=datetime.now(timezone.utc)))
        db.commit()
        _event(db, dep, f"Application reachable: {result.detail}")
        return
    dep.health_status = "unreachable"
    db.commit()
    fix = "Check the application's start command and that it listens on the PORT environment variable."
    if result.status_code in (401, 403) and dep.provider == "vercel":
        fix = "Vercel Deployment Protection is blocking public access. Disable it in Project Settings → Deployment Protection."
    elif result.status_code == 404:
        fix = "The server answered 404. Check the output directory (static sites) or add a / or /health route (APIs)."
    _fail(db, dep, f"Deployment exists but application is unreachable ({result.detail}).", fix)


async def run_destroy(deployment_id: int) -> None:
    with SessionLocal() as db:
        dep = db.get(Deployment, deployment_id)
        provider = get_provider(dep.provider)
        _event(db, dep, f"Destroying {provider.name} resource {dep.provider_resource_id}")
        try:
            await provider.destroy(dep)
        except (ApiError, ProviderNotConfigured) as exc:
            dep.status = dep.meta.get("status_before_destroy", S.FAILED)
            dep.error_message = f"Destroy failed: {exc}"
            db.commit()
            _event(db, dep, f"Destroy failed: {exc}", "error")
            return
        dep.status = S.DESTROYED
        dep.health_status = "unknown"
        db.commit()
        # Other deployments that shared this provider resource are gone too.
        for sibling in db.query(Deployment).filter(
            Deployment.provider == dep.provider,
            Deployment.provider_resource_id == dep.provider_resource_id,
            Deployment.id != dep.id,
            Deployment.status != S.DESTROYED,
        ):
            sibling.status = S.DESTROYED
        db.commit()
        _event(db, dep, f"{provider.name} resource removed")
