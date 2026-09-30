"""Continue with Google, bearer sessions, and per-user isolation."""
from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

import httpx
import respx


def test_api_requires_sign_in(anon_client):
    assert anon_client.get("/api/projects").status_code == 401
    assert anon_client.get("/api/stats").status_code == 401
    assert anon_client.get("/api/health").status_code == 200
    assert anon_client.get("/api/auth/config").json()["google_configured"] is True


def test_dev_login_disabled_by_default(anon_client):
    assert anon_client.post("/api/auth/dev-login").status_code == 404


@respx.mock
def test_continue_with_google_creates_user_and_session(anon_client, db):
    start = anon_client.get("/api/auth/google/start").json()["authorize_url"]
    q = parse_qs(urlparse(start).query)
    assert q["scope"] == ["openid email profile"]
    assert q["redirect_uri"] == ["https://api.clouddeploy.example/api/auth/google/callback"]

    respx.post("https://oauth2.googleapis.com/token").mock(return_value=httpx.Response(200, json={"access_token": "ya29.x"}))
    respx.get("https://openidconnect.googleapis.com/v1/userinfo").mock(return_value=httpx.Response(200, json={
        "sub": "1234", "email": "Shreya@Example.com", "email_verified": True, "name": "Shreya H", "picture": "https://p"}))
    resp = anon_client.get(f"/api/auth/google/callback?code=c&state={q['state'][0]}", follow_redirects=False)
    location = resp.headers["location"]
    assert location.startswith("https://clouddeploy.example/auth/callback#token=")
    token = unquote(location.split("#token=", 1)[1])

    me = anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "shreya@example.com" and me["name"] == "Shreya H"

    from backend.models import AuthSession
    assert token not in {s.token_hash for s in db.query(AuthSession).all()}  # only hashes stored

    anon_client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


@respx.mock
def test_unverified_google_email_is_rejected(anon_client):
    state = parse_qs(urlparse(anon_client.get("/api/auth/google/start").json()["authorize_url"]).query)["state"][0]
    respx.post("https://oauth2.googleapis.com/token").mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.get("https://openidconnect.googleapis.com/v1/userinfo").mock(return_value=httpx.Response(200, json={"sub": "9", "email": "x@y.z", "email_verified": False}))
    loc = anon_client.get(f"/api/auth/google/callback?code=c&state={state}", follow_redirects=False).headers["location"]
    assert "#error=" in loc


def test_users_cannot_see_each_others_projects(client, db, anon_client):
    from backend.models import Project, User
    from backend.services.auth import create_session

    other = User(email="other@example.com")
    db.add(other)
    db.commit()
    p = Project(user_id=other.id, name="secret", source_type="upload")
    db.add(p)
    db.commit()
    assert client.get("/api/projects").json() == []
    assert client.get(f"/api/projects/{p.id}").status_code == 404
    other_token = create_session(db, other)
    assert len(anon_client.get("/api/projects", headers={"Authorization": f"Bearer {other_token}"}).json()) == 1
