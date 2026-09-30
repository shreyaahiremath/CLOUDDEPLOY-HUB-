"""Provider abstraction. Each provider implements its own real deployment mechanism."""
from __future__ import annotations

import re
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from backend.services.deployment.capabilities import CATALOG, ProviderCapability

if TYPE_CHECKING:
    from backend.models import Deployment, Project
    from backend.services.github.client import GitHubClient


class ProviderNotConfigured(Exception):
    def __init__(self, provider: str, missing: list[str]):
        self.provider = provider
        self.missing = missing
        super().__init__(f"Provider Not Configured: set {', '.join(missing)} in backend/.env")


class DeployError(Exception):
    """A deployment failure with the provider's actual reason and a suggested fix."""

    def __init__(self, reason: str, suggested_fix: str | None = None):
        self.reason = reason
        self.suggested_fix = suggested_fix
        super().__init__(reason)


# Phases a provider reports. The worker maps them onto DeploymentStatus and adds health checks.
PHASE_QUEUED, PHASE_BUILDING, PHASE_DEPLOYING, PHASE_LIVE, PHASE_FAILED = "QUEUED", "BUILDING", "DEPLOYING", "LIVE", "FAILED"


@dataclass
class DeployConfig:
    branch: str | None = None
    name: str | None = None
    build_mode: str = "native"  # native | docker (Render only)
    install_command: str | None = None
    build_command: str | None = None
    output_dir: str | None = None
    start_command: str | None = None
    health_check_path: str | None = None
    env_vars: dict[str, str] = field(default_factory=dict)
    acknowledge_conditional: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> DeployConfig:
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class DeployContext:
    project: Project
    analysis: dict
    config: DeployConfig
    github: GitHubClient
    github_login: str | None
    log: Callable[[str], None]
    previous_resource_id: str | None = None
    previous_meta: dict = field(default_factory=dict)

    @property
    def root_dir(self) -> str:
        return self.project.root_dir or ""

    def pick(self, attr: str) -> str | None:
        """User override from the config, else the analyzer's detected value."""
        value = getattr(self.config, attr, None)
        return value if value not in (None, "") else self.analysis.get(attr)


@dataclass
class DeployHandle:
    deployment_id: str | None
    resource_id: str | None
    public_url: str | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class ProviderStatus:
    phase: str
    raw: str
    public_url: str | None = None
    error: str | None = None
    deployment_id: str | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class LogLine:
    ts: datetime | str | None
    message: str
    source: str
    level: str = "info"

    def to_dict(self) -> dict:
        ts = self.ts.isoformat() if isinstance(self.ts, datetime) else self.ts
        return {"ts": ts, "message": self.message, "source": self.source, "level": self.level}


class DeploymentProvider(ABC):
    key: str

    @property
    def capability(self) -> ProviderCapability:
        return CATALOG[self.key]

    @property
    def name(self) -> str:
        return self.capability.name

    @abstractmethod
    def missing_credentials(self) -> list[str]: ...

    def is_configured(self) -> bool:
        return not self.missing_credentials()

    def require_configured(self) -> None:
        missing = self.missing_credentials()
        if missing:
            raise ProviderNotConfigured(self.key, missing)

    @abstractmethod
    async def check_credentials(self, user_id: int | None = None) -> dict:
        """Call a cheap authenticated endpoint. Returns {"ok": bool, "account": str|None, "error": str|None}."""

    @abstractmethod
    def validate(self, ctx: DeployContext) -> tuple[list[str], list[str]]:
        """Return (errors, warnings) for deploying this project with this config."""

    @abstractmethod
    def preview(self, ctx: DeployContext) -> dict:
        """Describe exactly what will be created/changed. No side effects."""

    @abstractmethod
    async def deploy(self, ctx: DeployContext) -> DeployHandle: ...

    @abstractmethod
    async def get_status(self, deployment: Deployment) -> ProviderStatus: ...

    @abstractmethod
    async def get_logs(self, deployment: Deployment) -> list[LogLine]: ...

    @abstractmethod
    async def get_outputs(self, deployment: Deployment) -> dict:
        """Return at least {"public_url": ...} as reported by the provider."""

    @abstractmethod
    async def destroy(self, deployment: Deployment) -> None: ...


def slugify(value: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:max_len].strip("-")
    return slug or "app"


def unique_slug(value: str, max_len: int = 40) -> str:
    return f"{slugify(value, max_len - 5)}-{secrets.token_hex(2)}"
