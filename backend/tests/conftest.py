"""Test setup: isolated data dir + SQLite database, fake credentials, no real network (respx)."""
from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="cdh-test-")
os.environ["CDH_DATA_DIR"] = _TMP
os.environ["SECRET_KEY"] = "test-secret"
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SECRET_KEY"] = ""
os.environ.update({
    "RENDER_API_KEY": "rnd_test", "VERCEL_TOKEN": "vc_test", "NETLIFY_AUTH_TOKEN": "nf_test",
    "CLOUDFLARE_API_TOKEN": "cf_test", "CLOUDFLARE_ACCOUNT_ID": "acc123",
    "GITHUB_CLIENT_ID": "gh_client", "GITHUB_CLIENT_SECRET": "gh_secret", "GITHUB_TOKEN": "",
    "GOOGLE_CLIENT_ID": "google_client", "GOOGLE_CLIENT_SECRET": "google_secret", "DEV_LOGIN": "",
    "FRONTEND_URL": "https://clouddeploy.example", "BACKEND_URL": "https://api.clouddeploy.example",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.database import Base, SessionLocal, engine, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    init_db()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def user(db):
    from backend.models import User

    u = User(id=1, email="shreya@example.com", name="Shreya", google_sub="g-1")
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def token(db, user):
    from backend.services.auth import create_session

    return create_session(db, user)


@pytest.fixture
def anon_client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def client(anon_client, token):
    anon_client.headers["Authorization"] = f"Bearer {token}"
    return anon_client


@pytest.fixture
def connected_github(db, user):
    from datetime import datetime, timezone

    from backend.models import GitHubConnection
    from backend.services.security import encrypt

    db.add(GitHubConnection(
        user_id=user.id, entered_username="shreya-hiremath", verified_login="shreya-hiremath", github_user_id=1,
        token_encrypted=encrypt("gho_testtoken"), scopes="repo,workflow,read:user", auth_method="oauth",
        connected_at=datetime.now(timezone.utc),
    ))
    db.commit()
