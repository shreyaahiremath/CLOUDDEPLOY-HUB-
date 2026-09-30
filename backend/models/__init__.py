from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeploymentStatus:
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    BUILDING = "BUILDING"
    DEPLOYING = "DEPLOYING"
    HEALTH_CHECKING = "HEALTH_CHECKING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DESTROYING = "DESTROYING"
    DESTROYED = "DESTROYED"

    ACTIVE = {QUEUED, VALIDATING, BUILDING, DEPLOYING, HEALTH_CHECKING, DESTROYING}
    TERMINAL = {SUCCESS, FAILED, DESTROYED}


def _load(raw: str | None) -> Any:
    return json.loads(raw) if raw else None


class User(Base):
    """A person signed in with Google."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    """Server-side session. Only the SHA-256 of the bearer token is stored."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(20))  # "upload" | "github"
    github_owner: Mapped[str | None] = mapped_column(String(100))
    github_repo: Mapped[str | None] = mapped_column(String(100))
    repo_private: Mapped[bool | None] = mapped_column(Boolean)
    branch: Mapped[str | None] = mapped_column(String(200))
    root_dir: Mapped[str] = mapped_column(String(300), default="")
    workspace_path: Mapped[str | None] = mapped_column(String(500))
    upload_report_json: Mapped[str | None] = mapped_column(Text)
    analysis_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    deployments: Mapped[list[Deployment]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Deployment.id.desc()"
    )

    @property
    def analysis(self) -> dict | None:
        return _load(self.analysis_json)

    @property
    def upload_report(self) -> dict | None:
        return _load(self.upload_report_json)

    @property
    def repository(self) -> str | None:
        if self.github_owner and self.github_repo:
            return f"{self.github_owner}/{self.github_repo}"
        return None


class ProjectSource(Base):
    """Uploaded source kept as a zip in the database, so uploads survive restarts on hosts with
    ephemeral disks (Render free instances). The on-disk workspace is only a cache."""

    __tablename__ = "project_sources"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    archive: Mapped[bytes] = mapped_column(LargeBinary)
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    project_name: Mapped[str] = mapped_column(String(120))
    github_username: Mapped[str | None] = mapped_column(String(100))
    repository: Mapped[str | None] = mapped_column(String(200))
    branch: Mapped[str | None] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(40))
    deployment_id: Mapped[str | None] = mapped_column(String(200))  # provider's deploy id
    provider_resource_id: Mapped[str | None] = mapped_column(String(200))  # service/project/site id
    status: Mapped[str] = mapped_column(String(20), default=DeploymentStatus.QUEUED)
    provider_status: Mapped[str | None] = mapped_column(String(60))  # raw status string from provider
    public_url: Mapped[str | None] = mapped_column(String(500))
    health_status: Mapped[str] = mapped_column(String(20), default="unknown")  # unknown|healthy|unreachable
    health_detail: Mapped[str | None] = mapped_column(Text)
    config_json: Mapped[str | None] = mapped_column(Text)
    meta_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    suggested_fix: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="deployments")
    events: Mapped[list[DeploymentEvent]] = relationship(
        back_populates="deployment", cascade="all, delete-orphan", order_by="DeploymentEvent.id"
    )

    @property
    def config(self) -> dict:
        return _load(self.config_json) or {}

    @property
    def meta(self) -> dict:
        return _load(self.meta_json) or {}

    def set_meta(self, **values: Any) -> None:
        self.meta_json = json.dumps({**self.meta, **values})


class DeploymentEvent(Base):
    """Orchestration events emitted by CloudDeploy Hub itself (e.g. "Created Render service").
    Provider build logs are never stored here; they are fetched live from the provider."""

    __tablename__ = "deployment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[int] = mapped_column(ForeignKey("deployments.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text)

    deployment: Mapped[Deployment] = relationship(back_populates="events")


class GitHubConnection(Base):
    """One GitHub connection per user. The token is Fernet-encrypted at rest and never sent
    to the frontend."""

    __tablename__ = "github_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    entered_username: Mapped[str | None] = mapped_column(String(100))
    verified_login: Mapped[str | None] = mapped_column(String(100))
    github_user_id: Mapped[int | None] = mapped_column(Integer)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    token_encrypted: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[str | None] = mapped_column(String(300))
    auth_method: Mapped[str | None] = mapped_column(String(20))  # oauth | server_token
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OAuthState(Base):
    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(100), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(20), default="github")  # github | google
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderVerification(Base):
    """Written only when a real deployment on this provider reached SUCCESS with a healthy URL."""

    __tablename__ = "provider_verifications"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    deployment_id: Mapped[int] = mapped_column(Integer)
    public_url: Mapped[str] = mapped_column(String(500))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
