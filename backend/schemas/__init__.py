"""Request models (Pydantic) and response serializers."""
from __future__ import annotations

import re
from datetime import timezone

from pydantic import BaseModel, Field, field_validator

from backend.models import Deployment, Project
from backend.services.security import public_config

ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class UsernameIn(BaseModel):
    username: str = Field(min_length=1, max_length=40)

    @field_validator("username")
    @classmethod
    def strip_at(cls, v: str) -> str:
        return v.strip().lstrip("@")


class GitHubProjectIn(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    branch: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, max_length=120)


class ProjectUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    root_dir: str | None = Field(default=None, max_length=300)
    branch: str | None = Field(default=None, max_length=200)

    @field_validator("root_dir")
    @classmethod
    def safe_root(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().strip("/")
        if ".." in v.split("/") or "\\" in v:
            raise ValueError("Root directory must be a relative folder inside the project")
        return v


class PublishIn(BaseModel):
    repo_name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    private: bool = True


class DeployConfigIn(BaseModel):
    branch: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, max_length=60)
    build_mode: str = Field(default="native", pattern="^(native|docker)$")
    install_command: str | None = Field(default=None, max_length=500)
    build_command: str | None = Field(default=None, max_length=500)
    output_dir: str | None = Field(default=None, max_length=200)
    start_command: str | None = Field(default=None, max_length=500)
    health_check_path: str | None = Field(default=None, max_length=200)
    env_vars: dict[str, str] = Field(default_factory=dict)
    acknowledge_conditional: bool = False

    @field_validator("env_vars")
    @classmethod
    def valid_env(cls, v: dict[str, str]) -> dict[str, str]:
        bad = [k for k in v if not ENV_KEY.match(k)]
        if bad:
            raise ValueError(f"Invalid environment variable name(s): {', '.join(bad)}")
        return v

    @field_validator("output_dir")
    @classmethod
    def safe_output(cls, v: str | None) -> str | None:
        if v and (".." in v.replace("\\", "/").split("/") or v.startswith("/")):
            raise ValueError("Output directory must be relative to the project")
        return v or None


class DeployIn(BaseModel):
    provider: str
    config: DeployConfigIn = Field(default_factory=DeployConfigIn)


def iso(dt) -> str | None:
    if not dt:
        return None
    return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).isoformat()


def project_out(p: Project, *, detail: bool = False) -> dict:
    deployments = p.deployments
    latest = deployments[0] if deployments else None
    out = {
        "id": p.id,
        "name": p.name,
        "source_type": p.source_type,
        "repository": p.repository,
        "repo_private": p.repo_private,
        "branch": p.branch,
        "root_dir": p.root_dir,
        "framework": (p.analysis or {}).get("framework"),
        "app_type": (p.analysis or {}).get("app_type"),
        "language": (p.analysis or {}).get("language"),
        "deployment_count": len(deployments),
        "live_count": sum(1 for d in deployments if d.status == "SUCCESS"),
        "latest_deployment": deployment_out(latest) if latest else None,
        "has_workspace": bool(p.workspace_path),
        "created_at": iso(p.created_at),
        "updated_at": iso(p.updated_at),
    }
    if detail:
        out["analysis"] = p.analysis
        out["upload_report"] = p.upload_report
        out["deployments"] = [deployment_out(d) for d in deployments]
    return out


def deployment_out(d: Deployment, *, events: bool = False) -> dict:
    out = {
        "id": d.id,
        "project_id": d.project_id,
        "project_name": d.project_name,
        "github_username": d.github_username,
        "repository": d.repository,
        "branch": d.branch,
        "source_type": d.source_type,
        "provider": d.provider,
        "deployment_id": d.deployment_id,
        "provider_resource_id": d.provider_resource_id,
        "status": d.status,
        "provider_status": d.provider_status,
        "public_url": d.public_url,
        "health_status": d.health_status,
        "health_detail": d.health_detail,
        "error_message": d.error_message,
        "suggested_fix": d.suggested_fix,
        "config": public_config(d.config),
        "links": {k: v for k, v in (d.meta.get("outputs") or {}).items() if k != "public_url" and v},
        "run_url": d.meta.get("run_url"),
        "created_at": iso(d.created_at),
        "updated_at": iso(d.updated_at),
        "finished_at": iso(d.finished_at),
    }
    if events:
        out["events"] = [
            {"ts": iso(e.ts), "level": e.level, "message": e.message, "source": "git2live"} for e in d.events
        ]
    return out
