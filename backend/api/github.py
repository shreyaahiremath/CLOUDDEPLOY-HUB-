from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import GitHubConnection, OAuthState, User
from backend.schemas import UsernameIn, iso
from backend.services.github import (
    GitHubClient,
    authorize_url,
    client_for,
    exchange_code,
    get_connection,
    get_token,
    valid_username,
)
from backend.services.auth import current_user
from backend.services.github.client import USERNAME_RULE
from backend.services.http import ApiError
from backend.services.security import encrypt, new_state

router = APIRouter(prefix="/api/github", tags=["github"])


def _conn(db: Session, user_id: int) -> GitHubConnection:
    conn = get_connection(db, user_id)
    if conn is None:
        conn = GitHubConnection(user_id=user_id)
        db.add(conn)
    return conn


def _status(conn: GitHubConnection | None) -> dict:
    connected = bool(conn and conn.verified_login)
    entered = conn.entered_username if conn else None
    verified = conn.verified_login if conn else None
    mismatch = bool(connected and entered and entered.lower() != (verified or "").lower())
    return {
        "oauth_configured": settings.github_oauth_configured,
        "server_token_available": bool(settings.github_token and settings.dev_login),
        "connected": connected,
        "entered_username": entered,
        "verified_login": verified,
        "avatar_url": conn.avatar_url if conn else None,
        "auth_method": conn.auth_method if connected else None,
        "scopes": (conn.scopes or "").split(",") if connected and conn.scopes else [],
        "connected_at": iso(conn.connected_at) if connected else None,
        "mismatch": mismatch,
        "mismatch_message": (
            f"You entered @{entered}, but GitHub authenticated @{verified}. Repositories will belong to @{verified}."
            if mismatch else None
        ),
        "callback_url": f"{settings.backend_url}/api/github/oauth/callback",
    }


@router.get("/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _status(get_connection(db, user.id))


@router.post("/username")
async def set_username(body: UsernameIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Store the username the user typed. This is an identity reference only, not authentication."""
    if not valid_username(body.username):
        raise HTTPException(422, f"'{body.username}' is not a valid GitHub username ({USERNAME_RULE}).")
    try:
        async with GitHubClient(get_token(db, user.id)) as gh:
            profile = await gh.get_public_user(body.username)
    except ApiError as exc:
        if exc.status == 404:
            raise HTTPException(404, f"GitHub has no user named @{body.username}.") from exc
        raise HTTPException(502, f"Could not check the username with GitHub: {exc.message}") from exc
    conn = _conn(db, user.id)
    conn.entered_username = profile.get("login", body.username)
    db.commit()
    return {**_status(conn), "public_repos": profile.get("public_repos")}


@router.get("/oauth/start")
def oauth_start(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if not settings.github_oauth_configured:
        raise HTTPException(
            400, "GitHub OAuth is not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in backend/.env."
        )
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    for stale in db.query(OAuthState).filter(OAuthState.created_at < cutoff).all():
        db.delete(stale)
    state = new_state()
    db.add(OAuthState(state=state, purpose="github", user_id=user.id))
    db.commit()
    return {"authorize_url": authorize_url(state)}


def _front(path: str, **params: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_url}{path}?{urlencode(params)}")


@router.get("/oauth/callback")
async def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if error:
        return _front("/github", error=error_description or error)
    record = db.get(OAuthState, state) if state else None
    if record is None or record.purpose != "github" or record.user_id is None or not code:
        return _front("/github", error="The sign-in link expired or was not started here. Try Connect GitHub again.")
    user_id = record.user_id
    db.delete(record)
    db.commit()
    try:
        token = await exchange_code(code)
        async with GitHubClient(token) as gh:
            user, scopes = await gh.get_user()
    except ApiError as exc:
        return _front("/github", error=f"GitHub sign-in failed: {exc.message}")
    conn = _conn(db, user_id)
    conn.verified_login = user["login"]
    conn.github_user_id = user["id"]
    conn.avatar_url = user.get("avatar_url")
    conn.token_encrypted = encrypt(token)
    conn.scopes = ",".join(scopes)
    conn.auth_method = "oauth"
    conn.connected_at = datetime.now(timezone.utc)
    if not conn.entered_username:
        conn.entered_username = user["login"]
    db.commit()
    return _front("/github", connected="1")


@router.post("/connect-server-token")
async def connect_server_token(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Local-development fallback (DEV_LOGIN=1 only): use GITHUB_TOKEN from backend/.env."""
    if not (settings.dev_login and settings.github_token):
        raise HTTPException(400, "The GITHUB_TOKEN fallback is only available in local development (DEV_LOGIN=1).")
    try:
        async with GitHubClient(settings.github_token) as gh:
            user, scopes = await gh.get_user()
    except ApiError as exc:
        raise HTTPException(400, f"GITHUB_TOKEN was rejected by GitHub: {exc.message}") from exc
    conn = _conn(db, user.id)
    conn.verified_login = user["login"]
    conn.github_user_id = user["id"]
    conn.avatar_url = user.get("avatar_url")
    conn.token_encrypted = None
    conn.scopes = ",".join(scopes)
    conn.auth_method = "server_token"
    conn.connected_at = datetime.now(timezone.utc)
    if not conn.entered_username:
        conn.entered_username = user["login"]
    db.commit()
    return _status(conn)


@router.post("/disconnect")
async def disconnect(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    conn = get_connection(db, user.id)
    if conn and conn.auth_method == "oauth" and settings.github_oauth_configured:
        token = get_token(db, user.id)
        if token:  # revoke the OAuth grant on GitHub's side too (best effort)
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    await client.request(
                        "DELETE", f"https://api.github.com/applications/{settings.github_client_id}/token",
                        auth=(settings.github_client_id, settings.github_client_secret),
                        json={"access_token": token}, headers={"Accept": "application/vnd.github+json"},
                    )
            except httpx.HTTPError:
                pass
    if conn:
        conn.verified_login = None
        conn.github_user_id = None
        conn.avatar_url = None
        conn.token_encrypted = None
        conn.scopes = None
        conn.auth_method = None
        conn.connected_at = None
        db.commit()
    return _status(conn)


def _require_connected(db: Session, user_id: int) -> None:
    if not get_token(db, user_id):
        raise HTTPException(401, "Connect GitHub first.")


@router.get("/repos")
async def repos(q: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _require_connected(db, user.id)
    try:
        async with client_for(db, user.id) as gh:
            items = await gh.list_repos()
    except ApiError as exc:
        raise HTTPException(502, f"GitHub: {exc.message}") from exc
    q = q.strip().lower()
    out = [
        {
            "owner": r["owner"]["login"], "name": r["name"], "full_name": r["full_name"],
            "private": r["private"], "default_branch": r.get("default_branch"),
            "description": r.get("description"), "language": r.get("language"),
            "updated_at": r.get("updated_at") or r.get("pushed_at"), "html_url": r["html_url"],
            "fork": r.get("fork", False), "archived": r.get("archived", False),
        }
        for r in items
        if not q or q in r["full_name"].lower() or q in (r.get("description") or "").lower()
    ]
    return {"total": len(items), "repositories": out}


@router.get("/repos/{owner}/{repo}/branches")
async def branches(owner: str, repo: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _require_connected(db, user.id)
    try:
        async with client_for(db, user.id) as gh:
            info = await gh.get_repo(owner, repo)
            items = await gh.list_branches(owner, repo)
    except ApiError as exc:
        raise HTTPException(exc.status if exc.status in (403, 404) else 502, f"GitHub: {exc.message}") from exc
    return {"default_branch": info.get("default_branch"), "branches": [b["name"] for b in items]}
