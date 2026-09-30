from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import OAuthState, User
from backend.services.auth import (
    bearer_token,
    create_session,
    current_user,
    google_authorize_url,
    google_profile,
    google_redirect_uri,
    revoke_session,
    upsert_google_user,
)
from backend.services.http import ApiError
from backend.services.security import new_state

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "avatar_url": user.avatar_url}


@router.get("/config")
def auth_config() -> dict:
    return {
        "google_configured": settings.google_configured,
        "dev_login": settings.dev_login,
        "google_redirect_uri": google_redirect_uri(),
    }


@router.get("/google/start")
def google_start(db: Session = Depends(get_db)) -> dict:
    if not settings.google_configured:
        raise HTTPException(400, "Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET on the backend.")
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    db.query(OAuthState).filter(OAuthState.created_at < cutoff).delete()
    state = new_state()
    db.add(OAuthState(state=state, purpose="google"))
    db.commit()
    return {"authorize_url": google_authorize_url(state)}


def _to_front(fragment: str) -> RedirectResponse:
    # Token travels in the URL fragment: it is never sent to a server or written to access logs.
    return RedirectResponse(f"{settings.frontend_url}/auth/callback#{fragment}")


@router.get("/google/callback")
async def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if error:
        return _to_front("error=" + quote("Google sign-in was cancelled." if error == "access_denied" else error))
    record = db.get(OAuthState, state) if state else None
    if record is None or record.purpose != "google" or not code:
        return _to_front("error=" + quote("The sign-in link expired. Try Continue with Google again."))
    db.delete(record)
    db.commit()
    try:
        profile = await google_profile(code)
    except ApiError as exc:
        return _to_front("error=" + quote(f"Google sign-in failed: {exc.message}"))
    user = upsert_google_user(db, profile)
    return _to_front("token=" + quote(create_session(db, user)))


@router.post("/dev-login")
def dev_login(db: Session = Depends(get_db)) -> dict:
    """Local development without Google credentials. Disabled unless DEV_LOGIN=1."""
    if not settings.dev_login:
        raise HTTPException(404, "Not found.")
    user = db.query(User).filter(User.email == "dev@localhost").one_or_none()
    if user is None:
        user = User(email="dev@localhost", name="Local Developer")
        db.add(user)
        db.commit()
    return {"token": create_session(db, user), "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return user_out(user)


@router.post("/logout", status_code=204)
def logout(token: str | None = Depends(bearer_token), db: Session = Depends(get_db)) -> None:
    if token:
        revoke_session(db, token)
