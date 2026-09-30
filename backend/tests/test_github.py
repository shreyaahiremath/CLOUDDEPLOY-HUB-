"""GitHub username validation, OAuth, repository and branch retrieval, repository selection."""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import respx

from backend.services.github.client import valid_username

API = "https://api.github.com"


def test_username_rules():
    assert valid_username("shreya-hiremath")
    assert valid_username("a")
    for bad in ("", "-abc", "abc-", "ab--c", "a" * 40, "has space", "under_score"):
        assert not valid_username(bad), bad


@respx.mock
def test_username_is_checked_but_not_treated_as_auth(client):
    respx.get(f"{API}/users/shreya-hiremath").mock(return_value=httpx.Response(200, json={"login": "shreya-hiremath", "public_repos": 7}))
    resp = client.post("/api/github/username", json={"username": "@shreya-hiremath"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["entered_username"] == "shreya-hiremath" and body["connected"] is False
    respx.get(f"{API}/users/nobody-here-xyz").mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
    assert client.post("/api/github/username", json={"username": "nobody-here-xyz"}).status_code == 404
    assert client.post("/api/github/username", json={"username": "bad--name"}).status_code == 422


@respx.mock
def test_oauth_flow_stores_encrypted_token_and_flags_mismatch(client, db):
    respx.get(f"{API}/users/shreya-hiremath").mock(return_value=httpx.Response(200, json={"login": "shreya-hiremath"}))
    client.post("/api/github/username", json={"username": "shreya-hiremath"})

    start = client.get("/api/github/oauth/start").json()["authorize_url"]
    q = parse_qs(urlparse(start).query)
    assert q["scope"] == ["repo workflow read:user"] and q["client_id"] == ["gh_client"]
    state = q["state"][0]

    respx.post("https://github.com/login/oauth/access_token").mock(return_value=httpx.Response(200, json={"access_token": "gho_secret_value"}))
    respx.get(f"{API}/user").mock(return_value=httpx.Response(
        200, json={"login": "someone-else", "id": 9, "avatar_url": "x"}, headers={"x-oauth-scopes": "repo, workflow, read:user"}))
    resp = client.get(f"/api/github/oauth/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.status_code in (302, 307) and "connected=1" in resp.headers["location"]

    status = client.get("/api/github/status").json()
    assert status["connected"] and status["verified_login"] == "someone-else"
    assert status["mismatch"] and "someone-else" in status["mismatch_message"]
    assert "gho_secret_value" not in str(status)

    from backend.models import GitHubConnection
    row = db.get(GitHubConnection, 1)
    assert row.token_encrypted and "gho_secret_value" not in row.token_encrypted

    # replayed state is rejected
    again = client.get(f"/api/github/oauth/callback?code=abc&state={state}", follow_redirects=False)
    assert "error=" in again.headers["location"]


@respx.mock
def test_repositories_branches_and_selection(client, connected_github):
    respx.get(f"{API}/user/repos").mock(return_value=httpx.Response(200, json=[
        {"owner": {"login": "shreya-hiremath"}, "name": "weather-api", "full_name": "shreya-hiremath/weather-api",
         "private": False, "default_branch": "main", "html_url": "https://github.com/shreya-hiremath/weather-api"},
        {"owner": {"login": "shreya-hiremath"}, "name": "portfolio", "full_name": "shreya-hiremath/portfolio",
         "private": True, "default_branch": "main", "html_url": "https://github.com/shreya-hiremath/portfolio"},
    ]))
    repos = client.get("/api/github/repos?q=weather").json()
    assert repos["total"] == 2 and [r["name"] for r in repos["repositories"]] == ["weather-api"]

    respx.get(f"{API}/repos/shreya-hiremath/weather-api").mock(return_value=httpx.Response(200, json={
        "name": "weather-api", "owner": {"login": "shreya-hiremath"}, "private": False, "default_branch": "main"}))
    respx.get(f"{API}/repos/shreya-hiremath/weather-api/branches").mock(return_value=httpx.Response(200, json=[{"name": "main"}, {"name": "dev"}]))
    branches = client.get("/api/github/repos/shreya-hiremath/weather-api/branches").json()
    assert branches == {"default_branch": "main", "branches": ["main", "dev"]}

    respx.get(f"{API}/repos/shreya-hiremath/weather-api/git/trees/dev").mock(return_value=httpx.Response(200, json={"tree": [
        {"path": "requirements.txt", "type": "blob"}, {"path": "app/main.py", "type": "blob"}]}))
    respx.get(f"{API}/repos/shreya-hiremath/weather-api/contents/requirements.txt").mock(return_value=httpx.Response(200, content=b"fastapi\nuvicorn\n"))
    respx.get(f"{API}/repos/shreya-hiremath/weather-api/contents/app/main.py").mock(return_value=httpx.Response(200, content=b"from fastapi import FastAPI\napp = FastAPI()\n"))
    resp = client.post("/api/projects/github", json={"owner": "shreya-hiremath", "repo": "weather-api", "branch": "dev"})
    assert resp.status_code == 201, resp.text
    project = resp.json()
    assert project["repository"] == "shreya-hiremath/weather-api" and project["branch"] == "dev"
    assert project["analysis"]["framework"] == "FastAPI"

    compat = {p["provider"]: p["status"] for p in client.get(f"/api/projects/{project['id']}/compatibility").json()["providers"]}
    assert compat == {"render": "compatible", "vercel": "conditional", "netlify": "incompatible",
                      "github_pages": "incompatible", "cloudflare_pages": "incompatible"}


def test_repos_require_connection(client):
    assert client.get("/api/github/repos").status_code == 401
