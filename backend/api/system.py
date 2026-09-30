from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config import PROJECT_ROOT, settings
from backend.database import get_db
from backend.models import Deployment, DeploymentStatus as S, Project, ProviderVerification, User
from backend.services.auth import current_user
from backend.schemas import deployment_out, iso
from backend.services.deployment import all_providers
from backend.services.deployment.capabilities import CATALOG, FREE_PLAN_NOTICE
from backend.services import supabase_store
from backend.services.github import get_connection
from backend.services.supabase_store import as_utc

router = APIRouter(prefix="/api", tags=["system"])

DOCS = {
    "readme": PROJECT_ROOT / "README.md",
    "architecture": PROJECT_ROOT / "docs" / "architecture.md",
    "deployment-guide": PROJECT_ROOT / "docs" / "deployment-guide.md",
    "github-integration": PROJECT_ROOT / "docs" / "github-integration.md",
    "provider-guide": PROJECT_ROOT / "docs" / "provider-guide.md",
    "project-report-content": PROJECT_ROOT / "docs" / "project-report-content.md",
    "faqs": PROJECT_ROOT / "docs" / "faqs.md",
    "troubleshooting": PROJECT_ROOT / "docs" / "troubleshooting.md",
}


@router.get("/health")
def health() -> dict:
    db_status = supabase_store.store.status()
    return {"status": "ok" if db_status["ok"] else "degraded", "service": "clouddeploy-hub", **db_status}


@router.get("/stats")
def stats(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    mine = db.query(Deployment).filter(Deployment.user_id == user.id)
    counts = dict(mine.with_entities(Deployment.status, func.count()).group_by(Deployment.status).all())
    conn = get_connection(db, user.id)
    recent = mine.order_by(Deployment.id.desc()).limit(6).all()
    return {
        "projects": db.query(func.count(Project.id)).filter(Project.user_id == user.id).scalar(),
        "deployments": sum(counts.values()),
        "successful": counts.get(S.SUCCESS, 0),
        "failed": counts.get(S.FAILED, 0),
        "in_progress": sum(v for k, v in counts.items() if k in S.ACTIVE),
        "live": counts.get(S.SUCCESS, 0),
        "github_connected": bool(conn and conn.verified_login),
        "github_login": conn.verified_login if conn else None,
        "free_platforms": len(CATALOG),
        "configured_platforms": sum(1 for p in all_providers() if p.is_configured()),
        "recent": [deployment_out(d) for d in recent],
        "timeline": _timeline(mine.all()),
        "by_provider": _by_provider(mine.all()),
    }


def _timeline(rows: list[Deployment], days: int = 14) -> list[dict]:
    """Deployments per day for the last `days` days (UTC), oldest first. Real counts only."""
    today = datetime.now(timezone.utc).date()
    buckets = {today - timedelta(days=i): {"total": 0, "success": 0, "failed": 0} for i in range(days)}
    for d in rows:
        day = as_utc(d.created_at).date()
        if day in buckets:
            buckets[day]["total"] += 1
            if d.status == S.SUCCESS:
                buckets[day]["success"] += 1
            elif d.status == S.FAILED:
                buckets[day]["failed"] += 1
    return [{"date": day.isoformat(), **buckets[day]} for day in sorted(buckets)]


def _by_provider(rows: list[Deployment]) -> list[dict]:
    out = []
    for p in all_providers():
        mine = [d for d in rows if d.provider == p.key]
        out.append({
            "provider": p.key, "name": p.name, "total": len(mine),
            "success": sum(1 for d in mine if d.status == S.SUCCESS),
        })
    return out


@router.get("/providers")
def providers(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    verified = {v.provider: v for v in db.query(ProviderVerification).all()}
    out = []
    for p in all_providers():
        v = verified.get(p.key)
        out.append({
            **p.capability.to_dict(),
            "configured": p.is_configured(),
            "missing_credentials": p.missing_credentials(),
            "verified": bool(v),
            "verification": {"deployment_id": v.deployment_id, "public_url": v.public_url, "verified_at": iso(v.verified_at)} if v else None,
            "free_plan_notice": FREE_PLAN_NOTICE,
        })
    return out


@router.post("/providers/{key}/check")
async def check_provider(key: str, user: User = Depends(current_user)) -> dict:
    match = next((p for p in all_providers() if p.key == key), None)
    if match is None:
        raise HTTPException(404, "Unknown provider.")
    return await match.check_credentials(user.id)


@router.get("/settings")
def get_settings(user: User = Depends(current_user)) -> dict:
    return {
        "backend_url": settings.backend_url,
        "frontend_url": settings.frontend_url,
        "github_oauth_configured": settings.github_oauth_configured,
        "github_callback_url": f"{settings.backend_url}/api/github/oauth/callback",
        "github_server_token": bool(settings.github_token and settings.dev_login),
        "google_configured": settings.google_configured,
        "dev_login": settings.dev_login,
        "database": supabase_store.store.status(),
        "env": {
            name: bool(value) for name, value in {
                "GOOGLE_CLIENT_ID": settings.google_client_id,
                "GOOGLE_CLIENT_SECRET": settings.google_client_secret,
                "SUPABASE_URL": settings.supabase_url,
                "SUPABASE_SECRET_KEY": settings.supabase_secret_key,
                "GITHUB_CLIENT_ID": settings.github_client_id,
                "GITHUB_CLIENT_SECRET": settings.github_client_secret,
                "GITHUB_TOKEN": settings.github_token,
                "RENDER_API_KEY": settings.render_api_key,
                "VERCEL_TOKEN": settings.vercel_token,
                "NETLIFY_AUTH_TOKEN": settings.netlify_auth_token,
                "CLOUDFLARE_API_TOKEN": settings.cloudflare_api_token,
                "CLOUDFLARE_ACCOUNT_ID": settings.cloudflare_account_id,
            }.items()
        },
        "limits": {
            "max_upload_mb": settings.max_upload_bytes // 1_048_576,
            "max_file_mb": settings.max_file_bytes // 1_048_576,
            "max_files": settings.max_files,
        },
    }


@router.get("/docs/{name}")
def doc(name: str) -> dict:
    path = DOCS.get(name)
    if path is None or not path.exists():
        raise HTTPException(404, "Document not found.")
    return {"name": name, "markdown": path.read_text(encoding="utf-8")}
