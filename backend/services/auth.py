"""Continue with Google (OpenID Connect authorization-code flow) + bearer-token sessions.

The frontend (Vercel) and API (Render) live on different sites, so sessions use an
`Authorization: Bearer` token instead of third-party cookies. Only its SHA-256 is stored.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import AuthSession, User
from backend.services.http import ApiError, extract_message

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"


def google_redirect_uri() -> str:
    return f"{settings.backend_url}/api/auth/google/callback"


def google_authorize_url(state: str) -> str:
    return GOOGLE_AUTH + "?" + urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
        "access_type": "online",
    })


async def google_profile(code: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(GOOGLE_TOKEN, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": google_redirect_uri(),
            "grant_type": "authorization_code",
        })
        if not resp.is_success:
            raise ApiError("Google", resp.status_code, extract_message(resp))
        access_token = resp.json()["access_token"]
        info = await client.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {access_token}"})
        if not info.is_success:
            raise ApiError("Google", info.status_code, extract_message(info))
    profile = info.json()
    if not profile.get("email") or not profile.get("email_verified"):
        raise ApiError("Google", 400, "Your Google account has no verified email address.")
    return profile


def upsert_google_user(db: Session, profile: dict) -> User:
    user = db.query(User).filter(User.google_sub == profile["sub"]).one_or_none()
    if user is None:
        user = db.query(User).filter(User.email == profile["email"].lower()).one_or_none()
    if user is None:
        user = User(email=profile["email"].lower())
        db.add(user)
    user.google_sub = profile["sub"]
    user.name = profile.get("name")
    user.avatar_url = profile.get("picture")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return user


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    for expired in db.query(AuthSession).filter(AuthSession.expires_at < now).all():
        db.delete(expired)
    db.add(AuthSession(token_hash=_hash(token), user_id=user.id, expires_at=now + timedelta(days=settings.session_days)))
    db.commit()
    return token


def revoke_session(db: Session, token: str) -> None:
    session = db.get(AuthSession, _hash(token))
    if session is not None:
        db.delete(session)
        db.commit()


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    token = _bearer(authorization)
    if not token:
        raise HTTPException(401, "Sign in to continue.")
    session = db.get(AuthSession, _hash(token))
    expires = session.expires_at if session else None
    if expires is not None and expires.tzinfo is None:  # SQLite returns naive datetimes
        expires = expires.replace(tzinfo=timezone.utc)
    if session is None or expires < datetime.now(timezone.utc):
        raise HTTPException(401, "Your session expired. Sign in again.")
    return session.user


def bearer_token(authorization: str | None = Header(default=None)) -> str | None:
    return _bearer(authorization)
