"""GitHub identity, OAuth and token access. Tokens never leave the backend."""
from __future__ import annotations

from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import GitHubConnection
from backend.services.github.client import GitHubClient, valid_username
from backend.services.http import ApiError, extract_message
from backend.services.security import decrypt

# repo: private repos + create/push; workflow: add GitHub Actions workflow files; read:user: identity.
OAUTH_SCOPES = "repo workflow read:user"

__all__ = ["GitHubClient", "valid_username", "get_connection", "get_token", "client_for", "authorize_url", "exchange_code"]


def get_connection(db: Session, user_id: int) -> GitHubConnection | None:
    return db.query(GitHubConnection).filter(GitHubConnection.user_id == user_id).one_or_none()


def get_token(db: Session, user_id: int) -> str | None:
    conn = get_connection(db, user_id)
    if conn is None or conn.verified_login is None:
        return None
    if conn.auth_method == "server_token":  # local development fallback only
        return settings.github_token if settings.dev_login and settings.github_token else None
    return decrypt(conn.token_encrypted) if conn.token_encrypted else None


def client_for(db: Session, user_id: int) -> GitHubClient:
    return GitHubClient(get_token(db, user_id))


def authorize_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": f"{settings.backend_url}/api/github/oauth/callback",
            "scope": OAUTH_SCOPES,
            "state": state,
            "allow_signup": "true",
        }
    )
    return f"https://github.com/login/oauth/authorize?{query}"


async def exchange_code(code: str) -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": f"{settings.backend_url}/api/github/oauth/callback",
            },
            headers={"Accept": "application/json"},
        )
    data = resp.json() if resp.content else {}
    if not resp.is_success or "access_token" not in data:
        raise ApiError("GitHub OAuth", resp.status_code, data.get("error_description") or extract_message(resp))
    return data["access_token"]
