"""Supabase (HTTPS API) as the durable store: startup load, write-back, deletes, bad configuration."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from backend.database import Base, SessionLocal, engine
from backend.models import AuthSession, Project, User
from backend.services import supabase_store
from backend.services.supabase_store import SupabaseStore

URL = "https://proj.supabase.co"
REST = f"{URL}/rest/v1"


@pytest.fixture
def store(monkeypatch):
    s = SupabaseStore()
    monkeypatch.setattr(supabase_store, "store", s)
    yield s
    s.ready = False


def mock_tables(rows: dict[str, list[dict]] | None = None):
    rows = rows or {}
    for table in Base.metadata.sorted_tables:
        respx.get(f"{REST}/{table.name}").mock(return_value=httpx.Response(200, json=rows.get(table.name, [])))
    respx.post(f"{URL}/storage/v1/bucket").mock(return_value=httpx.Response(200, json={}))


@respx.mock
def test_startup_loads_supabase_rows_into_local_db(store):
    mock_tables({
        "users": [{"id": 7, "google_sub": "g7", "email": "shreya@example.com", "name": "Shreya", "avatar_url": None,
                   "created_at": "2026-09-30T10:00:00+00:00", "last_login_at": None}],
        "projects": [{"id": 3, "user_id": 7, "name": "weather-api", "source_type": "github", "github_owner": "s", "github_repo": "w",
                      "repo_private": False, "branch": "main", "root_dir": "", "workspace_path": None, "upload_report_json": None,
                      "analysis_json": None, "created_at": "2026-09-30T10:00:00+00:00", "updated_at": "2026-09-30T10:00:00+00:00"}],
    })
    store.configure(URL, "sb_secret_abc")
    store.bootstrap(engine, Base.metadata)
    assert store.ready and store.status() == {"database": "Supabase", "ok": True, "detail": None}
    with SessionLocal() as db:
        assert db.get(User, 7).email == "shreya@example.com"
        assert db.get(Project, 3).name == "weather-api"


@respx.mock
def test_commits_are_written_back_and_deletes_are_mirrored(store):
    mock_tables()
    upsert_user = respx.post(f"{REST}/users").mock(return_value=httpx.Response(201))
    upsert_session = respx.post(f"{REST}/auth_sessions").mock(return_value=httpx.Response(201))
    delete_session = respx.delete(f"{REST}/auth_sessions").mock(return_value=httpx.Response(204))
    store.configure(URL, "sb_secret_abc")
    store.bootstrap(engine, Base.metadata)

    from backend.services.auth import create_session, revoke_session
    with SessionLocal() as db:
        user = User(email="new@example.com", name="New")
        db.add(user)
        db.commit()
        token = create_session(db, user)
        store.flush()
        body = json.loads(upsert_user.calls[0].request.content)[0]
        assert body["email"] == "new@example.com" and body["id"] == user.id
        assert body["created_at"].endswith("+00:00")
        assert upsert_user.calls[0].request.url.params["on_conflict"] == "id"
        assert upsert_user.calls[0].request.headers["apikey"] == "sb_secret_abc"
        assert upsert_session.called

        revoke_session(db, token)
        store.flush()
        assert delete_session.called and "token_hash" in delete_session.calls[0].request.url.params
        assert db.query(AuthSession).count() == 0


@respx.mock
def test_rollback_sends_nothing(store):
    mock_tables()
    upsert = respx.post(f"{REST}/users").mock(return_value=httpx.Response(201))
    store.configure(URL, "sb_secret_abc")
    store.bootstrap(engine, Base.metadata)
    with SessionLocal() as db:
        db.add(User(email="ghost@example.com"))
        db.flush()
        db.rollback()
    store.flush()
    assert not upsert.called


@pytest.mark.parametrize("key", [
    "sb_publishable_xyz",
    "eyJhbGciOiJIUzI1NiJ9." + __import__("base64").urlsafe_b64encode(b'{"role":"anon"}').decode().rstrip("=") + ".sig",
])
def test_public_keys_are_refused(store, key):
    store.configure(URL, key)
    store.bootstrap(engine, Base.metadata)
    assert not store.ready and "secret key" in store.error
    assert store.status()["ok"] is False


def test_service_role_jwt_is_accepted(store):
    import base64
    key = "eyJhbGciOiJIUzI1NiJ9." + base64.urlsafe_b64encode(b'{"role":"service_role"}').decode().rstrip("=") + ".sig"
    store.configure(URL, key)
    assert store.enabled and store.error is None


@respx.mock
def test_missing_tables_gives_a_clear_instruction(store):
    respx.get(url__startswith=REST).mock(return_value=httpx.Response(404, json={"code": "PGRST205", "message": "Could not find the table"}))
    store.configure(URL, "sb_secret_abc")
    store.bootstrap(engine, Base.metadata)
    assert not store.ready and "schema.sql" in store.error


def test_without_supabase_the_app_uses_local_sqlite(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["database"] == "SQLite (local only)"


@respx.mock
def test_uploaded_source_is_restored_from_supabase_storage(store, client, db):
    mock_tables()
    respx.post(url__startswith=REST).mock(return_value=httpx.Response(201))
    put = respx.post(url__regex=rf"{URL}/storage/v1/object/project-sources/\d+\.zip").mock(return_value=httpx.Response(200, json={}))
    store.configure(URL, "sb_secret_abc")
    store.bootstrap(engine, Base.metadata)

    from backend.services.auth import create_session
    user = User(email="u@example.com")
    db.add(user)
    db.commit()
    headers = {"Authorization": f"Bearer {create_session(db, user)}"}
    files = [("files", ("index.html", b"<!doctype html><h1>hi</h1>", "text/html"))]
    project = client.post("/api/projects/upload", data={"name": "site", "paths": ["site/index.html"]}, files=files, headers=headers).json()
    assert put.called
    archive = put.calls[0].request.content

    # simulate a restart: local disk and the local blob row are gone, only Supabase Storage has the zip
    from backend.models import ProjectSource
    from backend.services import workspace
    workspace.delete_workspace(project["id"])
    db.delete(db.get(ProjectSource, project["id"]))
    db.commit()
    respx.get(f"{URL}/storage/v1/object/project-sources/{project['id']}.zip").mock(return_value=httpx.Response(200, content=archive))
    resp = client.post(f"/api/projects/{project['id']}/analyze", headers=headers)
    assert resp.status_code == 200 and resp.json()["analysis"]["framework_key"] == "static"
