"""Provider API contract tests (mocked HTTP). These check that each provider sends the documented
request shape and parses real response shapes. They are NOT evidence of a real deployment; that
is what scripts/acceptance_test.py is for."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from backend.models import Deployment, Project
from backend.services.deployment import get_provider
from backend.services.deployment.base import PHASE_BUILDING, PHASE_FAILED, PHASE_LIVE, DeployConfig, DeployContext
from backend.services.deployment.capabilities import evaluate
from backend.services.github.client import GitHubClient

STATIC = {"framework_key": "static", "framework": "Static HTML", "app_type": "Static Frontend", "output_dir": ".", "needs_build": False}
VITE = {"framework_key": "vite-react", "framework": "React (Vite)", "app_type": "Frontend", "build_command": "npm run build",
        "install_command": "npm ci", "output_dir": "dist", "needs_build": True, "package_manager": "npm"}
FASTAPI = {"framework_key": "fastapi", "framework": "FastAPI", "app_type": "Backend API", "language": "Python",
           "install_command": "pip install -r requirements.txt", "start_command": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
           "python_entry": "app.main:app", "has_dockerfile": False}


def run(coro):
    return asyncio.run(coro)


def make_ctx(tmp_path, analysis, *, repo=True, private=False, config=None, logs=None):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / "index.html").write_text("<h1>hi</h1>")
    project = Project(id=1, user_id=1, name="Weather API", source_type="github" if repo else "upload", root_dir="",
                      github_owner="shreya-hiremath" if repo else None, github_repo="weather-api" if repo else None,
                      repo_private=private, branch="main", workspace_path=None if repo else str(src))
    return DeployContext(project, analysis, DeployConfig.from_dict(config or {}), GitHubClient("gho_x"), "shreya-hiremath",
                         (logs if logs is not None else []).append)


def dep_row(provider, **kw) -> Deployment:
    d = Deployment(id=1, user_id=1, project_id=1, project_name="x", provider=provider, source_type="github", **kw)
    from datetime import datetime, timezone
    d.created_at = datetime.now(timezone.utc)
    return d


# ----- compatibility -----------------------------------------------------------------------
@pytest.mark.parametrize("analysis,expected", [
    (STATIC, {"render": "compatible", "vercel": "compatible", "netlify": "compatible", "github_pages": "compatible", "cloudflare_pages": "compatible"}),
    (VITE, {"render": "compatible", "vercel": "compatible", "netlify": "compatible", "github_pages": "compatible", "cloudflare_pages": "compatible"}),
    (FASTAPI, {"render": "compatible", "vercel": "conditional", "netlify": "incompatible", "github_pages": "incompatible", "cloudflare_pages": "incompatible"}),
    ({"framework_key": "python", "app_type": "Worker"}, {"render": "incompatible", "vercel": "incompatible", "netlify": "incompatible", "github_pages": "incompatible", "cloudflare_pages": "incompatible"}),
])
def test_compatibility_matrix(analysis, expected):
    assert {k: evaluate(analysis, k)["status"] for k in expected} == expected


# ----- Render ------------------------------------------------------------------------------
@respx.mock
def test_render_creates_free_web_service_and_reads_url(tmp_path):
    respx.get("https://api.render.com/v1/owners").mock(return_value=httpx.Response(200, json=[{"owner": {"id": "tea-1", "name": "Shreya"}, "cursor": "c"}]))
    create = respx.post("https://api.render.com/v1/services").mock(return_value=httpx.Response(201, json={
        "service": {"id": "srv-123", "serviceDetails": {"url": "https://weather-api-x1.onrender.com"}}, "deployId": "dep-9"}))
    handle = run(get_provider("render").deploy(make_ctx(tmp_path, FASTAPI, config={"env_vars": {"DEBUG": "0"}})))
    body = json.loads(create.calls[0].request.content)
    assert body["type"] == "web_service" and body["ownerId"] == "tea-1"
    assert body["repo"] == "https://github.com/shreya-hiremath/weather-api" and body["branch"] == "main"
    assert body["serviceDetails"]["plan"] == "free" and body["serviceDetails"]["runtime"] == "python"
    assert body["serviceDetails"]["envSpecificDetails"]["startCommand"].startswith("uvicorn app.main:app")
    assert body["envVars"] == [{"key": "DEBUG", "value": "0"}]
    assert (handle.deployment_id, handle.resource_id, handle.public_url) == ("dep-9", "srv-123", "https://weather-api-x1.onrender.com")


@respx.mock
def test_render_static_site_and_status_mapping(tmp_path):
    respx.get("https://api.render.com/v1/owners").mock(return_value=httpx.Response(200, json=[{"owner": {"id": "tea-1", "name": "S"}}]))
    create = respx.post("https://api.render.com/v1/services").mock(return_value=httpx.Response(201, json={"service": {"id": "srv-s", "serviceDetails": {"url": "https://s.onrender.com"}}, "deployId": "dep-1"}))
    run(get_provider("render").deploy(make_ctx(tmp_path, VITE)))
    body = json.loads(create.calls[0].request.content)
    assert body["type"] == "static_site" and body["serviceDetails"]["publishPath"] == "dist"
    assert body["serviceDetails"]["buildCommand"] == "npm ci && npm run build"

    route = respx.get("https://api.render.com/v1/services/srv-s/deploys/dep-1")
    d = dep_row("render", provider_resource_id="srv-s", deployment_id="dep-1")
    route.mock(return_value=httpx.Response(200, json={"id": "dep-1", "status": "build_in_progress"}))
    assert run(get_provider("render").get_status(d)).phase == PHASE_BUILDING
    route.mock(return_value=httpx.Response(200, json={"id": "dep-1", "status": "live"}))
    assert run(get_provider("render").get_status(d)).phase == PHASE_LIVE
    route.mock(return_value=httpx.Response(200, json={"id": "dep-1", "status": "build_failed"}))
    assert run(get_provider("render").get_status(d)).phase == PHASE_FAILED


@respx.mock
def test_render_rejection_surfaces_provider_error(tmp_path):
    from backend.services.deployment.base import DeployError
    respx.get("https://api.render.com/v1/owners").mock(return_value=httpx.Response(200, json=[{"owner": {"id": "tea-1"}}]))
    respx.post("https://api.render.com/v1/services").mock(return_value=httpx.Response(400, json={"message": "repository not accessible"}))
    with pytest.raises(DeployError) as err:
        run(get_provider("render").deploy(make_ctx(tmp_path, FASTAPI)))
    assert "repository not accessible" in err.value.reason and "GitHub" in err.value.suggested_fix


def test_render_requires_github_repo(tmp_path):
    errors, _ = get_provider("render").validate(make_ctx(tmp_path, FASTAPI, repo=False))
    assert any("GitHub" in e for e in errors)


# ----- Vercel ------------------------------------------------------------------------------
@respx.mock
def test_vercel_uploads_files_and_uses_production_alias(tmp_path):
    respx.post("https://api.vercel.com/v11/projects").mock(return_value=httpx.Response(200, json={"id": "prj_1", "name": "weather-api"}))
    upload = respx.post("https://api.vercel.com/v2/files").mock(return_value=httpx.Response(200, json={}))
    deploy = respx.post("https://api.vercel.com/v13/deployments").mock(return_value=httpx.Response(200, json={"id": "dpl_1", "url": "weather-api-abc.vercel.app", "readyState": "QUEUED"}))
    handle = run(get_provider("vercel").deploy(make_ctx(tmp_path, STATIC, repo=False)))
    assert upload.calls[0].request.headers["x-vercel-digest"]
    body = json.loads(deploy.calls[0].request.content)
    assert body["target"] == "production" and body["project"] == "prj_1" and body["files"][0]["file"] == "index.html"
    assert (handle.deployment_id, handle.resource_id) == ("dpl_1", "prj_1")

    respx.get("https://api.vercel.com/v13/deployments/dpl_1").mock(return_value=httpx.Response(200, json={
        "id": "dpl_1", "readyState": "READY", "url": "weather-api-abc.vercel.app", "alias": ["weather-api-git-main.vercel.app", "weather-api.vercel.app"]}))
    d = dep_row("vercel", deployment_id="dpl_1", provider_resource_id="prj_1", meta_json=json.dumps(handle.meta))
    assert run(get_provider("vercel").get_status(d)).phase == PHASE_LIVE
    assert run(get_provider("vercel").get_outputs(d))["public_url"] == "https://weather-api.vercel.app"


@respx.mock
def test_vercel_error_state_has_provider_message():
    respx.get("https://api.vercel.com/v13/deployments/dpl_2").mock(return_value=httpx.Response(200, json={"readyState": "ERROR", "errorMessage": "Command \"npm run build\" exited with 1"}))
    st = run(get_provider("vercel").get_status(dep_row("vercel", deployment_id="dpl_2")))
    assert st.phase == PHASE_FAILED and "exited with 1" in st.error


# ----- Netlify -----------------------------------------------------------------------------
@respx.mock
def test_netlify_build_api_upload(tmp_path):
    respx.post("https://api.netlify.com/api/v1/sites").mock(return_value=httpx.Response(201, json={"id": "site-1", "name": "weather-api", "ssl_url": "https://weather-api.netlify.app"}))
    build = respx.post("https://api.netlify.com/api/v1/sites/site-1/builds").mock(return_value=httpx.Response(200, json={"id": "b1", "deploy_id": "d1"}))
    handle = run(get_provider("netlify").deploy(make_ctx(tmp_path, VITE, repo=False)))
    req = build.calls[0].request
    assert b'name="zip"' in req.content and b'name="title"' in req.content
    assert (handle.deployment_id, handle.resource_id) == ("d1", "site-1")
    toml = get_provider("netlify")._toml(make_ctx(tmp_path, VITE, repo=False))
    assert 'command = "npm run build"' in toml and 'publish = "dist"' in toml and 'to = "/index.html"' in toml

    respx.get("https://api.netlify.com/api/v1/deploys/d1").mock(return_value=httpx.Response(200, json={"state": "ready", "deploy_ssl_url": "https://d1--weather-api.netlify.app"}))
    respx.get("https://api.netlify.com/api/v1/sites/site-1").mock(return_value=httpx.Response(200, json={"ssl_url": "https://weather-api.netlify.app"}))
    d = dep_row("netlify", deployment_id="d1", provider_resource_id="site-1")
    assert run(get_provider("netlify").get_status(d)).phase == PHASE_LIVE
    assert run(get_provider("netlify").get_outputs(d))["public_url"] == "https://weather-api.netlify.app"


# ----- GitHub Pages ------------------------------------------------------------------------
def test_github_pages_rejects_backend_and_private_repo(tmp_path, connected_github):
    p = get_provider("github_pages")
    errors, _ = p.validate(make_ctx(tmp_path, FASTAPI))
    assert any("static" in e for e in errors)
    errors, _ = p.validate(make_ctx(tmp_path, STATIC, private=True))
    assert any("public" in e for e in errors)


def test_github_pages_workflow_sets_vite_base(tmp_path, connected_github):
    wf = get_provider("github_pages").workflow(make_ctx(tmp_path, VITE))
    assert "npm run build -- --base=/weather-api/" in wf
    assert "actions/deploy-pages@v4" in wf and "workflow_dispatch" in wf and "404.html" in wf
    static_wf = get_provider("github_pages").workflow(make_ctx(tmp_path, STATIC))
    assert "rsync" in static_wf and "setup-node" not in static_wf


@respx.mock
def test_github_pages_deploy_and_status(tmp_path, connected_github):
    gh = "https://api.github.com/repos/shreya-hiremath/weather-api"
    respx.post(f"{gh}/pages").mock(return_value=httpx.Response(201, json={"html_url": "https://shreya-hiremath.github.io/weather-api/"}))
    respx.get(f"{gh}/contents/.github/workflows/clouddeploy-pages.yml").mock(return_value=httpx.Response(404, json={}))
    put = respx.put(f"{gh}/contents/.github/workflows/clouddeploy-pages.yml").mock(return_value=httpx.Response(201, json={}))
    respx.post(f"{gh}/actions/workflows/clouddeploy-pages.yml/dispatches").mock(return_value=httpx.Response(204))
    handle = run(get_provider("github_pages").deploy(make_ctx(tmp_path, STATIC)))
    assert put.called and handle.meta["workflow_file"] == "clouddeploy-pages.yml"

    d = dep_row("github_pages", provider_resource_id="shreya-hiremath/weather-api", meta_json=json.dumps({**handle.meta, "run_id": 77}))
    respx.get(f"{gh}/actions/runs/77").mock(return_value=httpx.Response(200, json={"id": 77, "status": "completed", "conclusion": "success", "html_url": "u"}))
    st = run(get_provider("github_pages").get_status(d))
    assert st.phase == PHASE_LIVE and st.deployment_id == "77"
    respx.get(f"{gh}/pages").mock(return_value=httpx.Response(200, json={"html_url": "https://shreya-hiremath.github.io/weather-api/"}))
    assert run(get_provider("github_pages").get_outputs(d))["public_url"] == "https://shreya-hiremath.github.io/weather-api/"


# ----- Cloudflare Pages --------------------------------------------------------------------
@respx.mock
def test_cloudflare_creates_project_sets_secrets_and_dispatches(tmp_path, connected_github):
    from nacl import encoding, public
    key = public.PrivateKey.generate().public_key.encode(encoding.Base64Encoder()).decode()
    gh = "https://api.github.com/repos/shreya-hiremath/weather-api"
    cf = "https://api.cloudflare.com/client/v4/accounts/acc123"
    create = respx.post(f"{cf}/pages/projects").mock(return_value=httpx.Response(200, json={"result": {"name": "weather-api", "subdomain": "weather-api.pages.dev"}}))
    respx.get(f"{gh}/actions/secrets/public-key").mock(return_value=httpx.Response(200, json={"key": key, "key_id": "k1"}))
    secret = respx.put(url__regex=rf"{gh}/actions/secrets/.*").mock(return_value=httpx.Response(201))
    respx.get(f"{gh}/contents/.github/workflows/clouddeploy-cloudflare.yml").mock(return_value=httpx.Response(404, json={}))
    put = respx.put(f"{gh}/contents/.github/workflows/clouddeploy-cloudflare.yml").mock(return_value=httpx.Response(201, json={}))
    respx.post(f"{gh}/actions/workflows/clouddeploy-cloudflare.yml/dispatches").mock(return_value=httpx.Response(204))
    handle = run(get_provider("cloudflare_pages").deploy(make_ctx(tmp_path, VITE)))
    assert json.loads(create.calls[0].request.content) == {"name": "weather-api", "production_branch": "main"}
    assert secret.call_count == 2 and "cf_test" not in secret.calls[0].request.content.decode()
    import base64
    workflow = base64.b64decode(json.loads(put.calls[0].request.content)["content"]).decode()
    assert "wrangler@4 pages deploy" in workflow and "--project-name=weather-api" in workflow
    assert handle.meta["subdomain"] == "weather-api.pages.dev"

