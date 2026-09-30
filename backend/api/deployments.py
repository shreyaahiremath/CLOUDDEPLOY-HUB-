from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Deployment, DeploymentStatus as S, Project, User
from backend.services.auth import current_user
from backend.schemas import DeployIn, deployment_out, iso
from backend.services.deployment import get_provider
from backend.services.deployment.base import DeployConfig, DeployContext
from backend.services.deployment.capabilities import (
    CATALOG,
    CONDITIONAL,
    FREE_PLAN_CHANGE_NOTICE,
    INCOMPATIBLE,
    evaluate,
)
from backend.services.deployment.health import check_once, paths_for
from backend.services.github import client_for, get_connection
from backend.services.http import ApiError
from backend.services.security import seal_env
from backend.workers import deployment_worker

router = APIRouter(prefix="/api", tags=["deployments"])


def _project(db: Session, project_id: int, user: User) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(404, "Project not found.")
    return project


def _deployment(db: Session, deployment_id: int, user: User) -> Deployment:
    dep = db.get(Deployment, deployment_id)
    if dep is None or dep.user_id != user.id:
        raise HTTPException(404, "Deployment not found.")
    return dep


def _provider(key: str):
    if key not in CATALOG:
        raise HTTPException(404, f"Unknown provider '{key}'.")
    return get_provider(key)


@router.post("/projects/{project_id}/preview")
async def preview(project_id: int, body: DeployIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    project = _project(db, project_id, user)
    provider = _provider(body.provider)
    verdict = evaluate(project.analysis, body.provider)
    config = DeployConfig.from_dict(body.config.model_dump())
    conn = get_connection(db, user.id)
    async with client_for(db, user.id) as gh:
        ctx = DeployContext(project, project.analysis or {}, config, gh, conn.verified_login if conn else None, lambda _m: None)
        errors, warnings = provider.validate(ctx)
        plan = provider.preview(ctx)
    missing = provider.missing_credentials()
    if verdict["status"] == INCOMPATIBLE:
        errors = verdict["reasons"] + errors
    return {
        "application": project.name,
        "source": "GitHub" if project.source_type == "github" else "Local Project",
        "repository": project.repository,
        "branch": config.branch or project.branch,
        "provider": body.provider,
        "provider_name": provider.name,
        "environment": "Production",
        "compatibility": verdict,
        "configured": not missing,
        "missing_credentials": missing,
        "errors": errors,
        "warnings": warnings,
        "plan": plan,
        "notice": FREE_PLAN_CHANGE_NOTICE,
        "can_deploy": not errors and not missing,
    }


@router.post("/projects/{project_id}/deployments", status_code=201)
def create_deployment(project_id: int, body: DeployIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    project = _project(db, project_id, user)
    provider = _provider(body.provider)
    verdict = evaluate(project.analysis, body.provider)
    if verdict["status"] == INCOMPATIBLE:
        raise HTTPException(400, f"{provider.name} is not compatible with this project: {' '.join(verdict['reasons'])}")
    if verdict["status"] == CONDITIONAL and not body.config.acknowledge_conditional:
        raise HTTPException(400, "This provider only works with adaptations. Confirm the warning to continue.")
    missing = provider.missing_credentials()
    if missing:
        raise HTTPException(400, f"Provider Not Configured: missing {', '.join(missing)}.")
    return deployment_out(_create(db, project, body.provider, body.config.model_dump()), events=True)


def _create(db: Session, project: Project, provider_key: str, config: dict, reuse_from: int | None = None) -> Deployment:
    conn = get_connection(db, project.user_id)
    dep = Deployment(
        user_id=project.user_id,
        project_id=project.id,
        project_name=project.name,
        github_username=conn.verified_login if conn and conn.verified_login else (conn.entered_username if conn else None),
        repository=project.repository,
        branch=config.get("branch") or project.branch,
        source_type=project.source_type,
        provider=provider_key,
        status=S.QUEUED,
        config_json=json.dumps(seal_env(config)),
        meta_json=json.dumps({"reuse_from": reuse_from} if reuse_from else {}),
    )
    db.add(dep)
    db.commit()
    deployment_worker.start(dep.id)
    return dep


@router.get("/deployments")
def list_deployments(provider: str | None = None, status: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    q = db.query(Deployment).filter(Deployment.user_id == user.id)
    if provider:
        q = q.filter(Deployment.provider == provider)
    if status:
        q = q.filter(Deployment.status == status)
    return [deployment_out(d) for d in q.order_by(Deployment.id.desc()).limit(500)]


@router.get("/deployments/{deployment_id}")
def get_deployment(deployment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    dep = _deployment(db, deployment_id, user)
    out = deployment_out(dep, events=True)
    out["provider_name"] = CATALOG[dep.provider].name
    out["plan"] = CATALOG[dep.provider].plan
    return out


@router.get("/deployments/{deployment_id}/logs")
async def deployment_logs(deployment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    dep = _deployment(db, deployment_id, user)
    provider = get_provider(dep.provider)
    provider_logs, provider_error = [], None
    if dep.provider_resource_id or dep.deployment_id:
        try:
            provider_logs = [line.to_dict() for line in await provider.get_logs(dep)]
        except ApiError as exc:
            provider_error = f"{exc.service}: {exc.message}"
        except Exception as exc:  # noqa: BLE001 - never 500 the log viewer
            provider_error = str(exc)
    return {
        "hub_events": [
            {"ts": iso(e.ts), "level": e.level, "message": e.message, "source": "clouddeploy-hub"}
            for e in dep.events
        ],
        "provider_logs": provider_logs,
        "provider_error": provider_error,
        "provider_name": provider.name,
    }


@router.post("/deployments/{deployment_id}/health")
async def recheck_health(deployment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    dep = _deployment(db, deployment_id, user)
    if not dep.public_url:
        raise HTTPException(400, "This deployment has no public URL yet.")
    app_type = (dep.project.analysis or {}).get("app_type")
    result = await check_once(dep.public_url, paths_for(app_type, dep.config.get("health_check_path")))
    if dep.status != S.DESTROYED:
        dep.health_status = "healthy" if result.healthy else "unreachable"
        dep.health_detail = result.detail
        db.commit()
    return {"healthy": result.healthy, "detail": result.detail, "status_code": result.status_code, "url": result.checked_url}


@router.post("/deployments/{deployment_id}/redeploy", status_code=201)
def redeploy(deployment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    dep = _deployment(db, deployment_id, user)
    if dep.status in S.ACTIVE:
        raise HTTPException(409, "This deployment is still in progress.")
    provider = get_provider(dep.provider)
    if provider.missing_credentials():
        raise HTTPException(400, f"Provider Not Configured: missing {', '.join(provider.missing_credentials())}.")
    reuse = dep.id if dep.provider_resource_id and dep.status != S.DESTROYED else None
    new = _create(db, dep.project, dep.provider, dep.config, reuse_from=reuse)
    return deployment_out(new, events=True)


@router.post("/deployments/{deployment_id}/destroy")
def destroy(deployment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    dep = _deployment(db, deployment_id, user)
    if dep.status == S.DESTROYED:
        raise HTTPException(409, "Already destroyed.")
    if dep.status in S.ACTIVE:
        raise HTTPException(409, "Wait for the deployment to finish before destroying it.")
    if not dep.provider_resource_id:
        dep.status = S.DESTROYED
        db.commit()
        return deployment_out(dep, events=True)
    dep.set_meta(status_before_destroy=dep.status)
    dep.status = S.DESTROYING
    db.commit()
    deployment_worker.start_destroy(dep.id)
    return deployment_out(dep, events=True)
