"""Deployment lifecycle: create, status polling, logs, URL extraction, health check, failure, destroy.
Provider calls are replaced with a scripted fake so the worker logic is tested without network."""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.models import Deployment, DeploymentStatus as S, Project, ProviderVerification
from backend.services.deployment import _PROVIDERS
from backend.services.deployment.base import (
    PHASE_BUILDING,
    PHASE_FAILED,
    PHASE_LIVE,
    DeployHandle,
    LogLine,
    ProviderStatus,
)
from backend.services.deployment.health import HealthResult
from backend.workers import deployment_worker


class FakeProvider:
    key = "render"
    name = "Render"

    def __init__(self, phases, url="https://weather-api.onrender.com", error=None):
        self.phases = list(phases)
        self.url = url
        self.error = error
        self.destroyed = False

    def missing_credentials(self):
        return []

    def is_configured(self):
        return True

    def require_configured(self):
        pass

    def validate(self, ctx):
        return [], []

    async def deploy(self, ctx):
        ctx.log("Creating Render web_service")
        return DeployHandle("dep-1", "srv-1", meta={"owner_id": "tea-1"})

    async def get_status(self, dep):
        phase = self.phases.pop(0) if len(self.phases) > 1 else self.phases[0]
        return ProviderStatus(phase, phase.lower(), error=self.error if phase == PHASE_FAILED else None)

    async def get_logs(self, dep):
        return [LogLine(None, "==> Build failed: pip exited 1", "render:build", "error")]

    async def get_outputs(self, dep):
        return {"public_url": self.url}

    async def destroy(self, dep):
        self.destroyed = True


@pytest.fixture
def project(db, user):
    p = Project(user_id=user.id, name="weather-api", source_type="github", github_owner="shreya-hiremath", github_repo="weather-api",
                branch="main", analysis_json=json.dumps({"app_type": "Backend API", "framework_key": "fastapi"}))
    db.add(p)
    db.commit()
    return p


def make_dep(db, project) -> Deployment:
    d = Deployment(user_id=project.user_id, project_id=project.id, project_name=project.name, repository=project.repository, branch="main",
                   source_type="github", provider="render", status=S.QUEUED, config_json="{}")
    db.add(d)
    db.commit()
    return d


@pytest.fixture
def fast(monkeypatch):
    from backend.config import settings
    object.__setattr__(settings, "poll_interval_seconds", 0)
    yield
    object.__setattr__(settings, "poll_interval_seconds", 5.0)


def run_with(monkeypatch, fake, health: HealthResult, dep_id: int):
    monkeypatch.setitem(_PROVIDERS, "render", fake)

    async def fake_health(url, paths, **kw):
        fake_health.called_with = (url, paths)
        return health

    monkeypatch.setattr(deployment_worker, "check_with_retries", fake_health)
    asyncio.run(deployment_worker.run_deployment(dep_id))
    return fake_health


def test_success_only_after_health_check(monkeypatch, db, project, fast):
    dep = make_dep(db, project)
    fake = FakeProvider([PHASE_BUILDING, PHASE_BUILDING, PHASE_LIVE])
    health = run_with(monkeypatch, fake, HealthResult(True, "GET /health returned HTTP 200", 200), dep.id)
    db.expire_all()
    dep = db.get(Deployment, dep.id)
    assert dep.status == S.SUCCESS and dep.health_status == "healthy"
    assert dep.public_url == "https://weather-api.onrender.com"  # URL from provider outputs
    assert dep.deployment_id == "dep-1" and dep.provider_resource_id == "srv-1"
    assert health.called_with == ("https://weather-api.onrender.com", ["/health", "/"])
    messages = [e.message for e in dep.events]
    assert any("Creating Render web_service" in m for m in messages)
    assert db.get(ProviderVerification, "render").deployment_id == dep.id


def test_unreachable_app_is_not_success(monkeypatch, db, project, fast):
    dep = make_dep(db, project)
    run_with(monkeypatch, FakeProvider([PHASE_LIVE]), HealthResult(False, "GET / returned HTTP 502", 502), dep.id)
    db.expire_all()
    dep = db.get(Deployment, dep.id)
    assert dep.status == S.FAILED and dep.health_status == "unreachable"
    assert "unreachable" in dep.error_message
    assert db.get(ProviderVerification, "render") is None


def test_provider_failure_includes_real_reason_and_log_tail(monkeypatch, db, project, fast):
    dep = make_dep(db, project)
    run_with(monkeypatch, FakeProvider([PHASE_BUILDING, PHASE_FAILED], error="Render deploy ended with status 'build_failed'"),
             HealthResult(True, "", 200), dep.id)
    db.expire_all()
    dep = db.get(Deployment, dep.id)
    assert dep.status == S.FAILED
    assert "build_failed" in dep.error_message and "pip exited 1" in dep.error_message
    assert dep.suggested_fix


def test_not_configured_provider_is_reported(client, db, project, monkeypatch):
    from backend.config import settings
    object.__setattr__(settings, "vercel_token", "")
    try:
        resp = client.post(f"/api/projects/{project.id}/deployments",
                           json={"provider": "vercel", "config": {"acknowledge_conditional": True}})
        assert resp.status_code == 400 and "Provider Not Configured" in resp.json()["detail"]
    finally:
        object.__setattr__(settings, "vercel_token", "vc_test")


def test_incompatible_and_conditional_are_blocked(client, project):
    resp = client.post(f"/api/projects/{project.id}/deployments", json={"provider": "github_pages"})
    assert resp.status_code == 400 and "not compatible" in resp.json()["detail"]
    resp = client.post(f"/api/projects/{project.id}/deployments", json={"provider": "vercel"})
    assert resp.status_code == 400 and "Confirm" in resp.json()["detail"]


def test_logs_endpoint_combines_hub_events_and_provider_logs(client, db, project, monkeypatch):
    dep = make_dep(db, project)
    dep.provider_resource_id = "srv-1"
    db.commit()
    monkeypatch.setitem(_PROVIDERS, "render", FakeProvider([PHASE_LIVE]))
    body = client.get(f"/api/deployments/{dep.id}/logs").json()
    assert body["provider_logs"][0]["source"] == "render:build"
    assert body["provider_error"] is None


def test_destroy_marks_destroyed(monkeypatch, db, project):
    dep = make_dep(db, project)
    dep.status, dep.provider_resource_id = S.SUCCESS, "srv-1"
    db.commit()
    fake = FakeProvider([PHASE_LIVE])
    monkeypatch.setitem(_PROVIDERS, "render", fake)
    asyncio.run(deployment_worker.run_destroy(dep.id))
    db.expire_all()
    assert fake.destroyed and db.get(Deployment, dep.id).status == S.DESTROYED


def test_project_with_live_deployments_cannot_be_deleted(client, db, project):
    dep = make_dep(db, project)
    dep.status = S.SUCCESS
    db.commit()
    assert client.delete(f"/api/projects/{project.id}").status_code == 409


def test_health_check_against_real_http(monkeypatch):
    """check_once treats 2xx as healthy and anything else as unreachable."""
    import httpx
    import respx

    from backend.services.deployment.health import check_once
    with respx.mock:
        respx.get("https://ok.example/health").mock(return_value=httpx.Response(404))
        respx.get("https://ok.example/").mock(return_value=httpx.Response(200))
        result = asyncio.run(check_once("https://ok.example", ["/health", "/"]))
        assert result.healthy and "/" in result.detail
        respx.get("https://down.example/").mock(side_effect=httpx.ConnectError("boom"))
        assert not asyncio.run(check_once("https://down.example", ["/"])).healthy
