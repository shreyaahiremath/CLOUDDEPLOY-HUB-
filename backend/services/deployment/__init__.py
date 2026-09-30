"""Provider registry."""
from __future__ import annotations

from backend.database import SessionLocal
from backend.services.deployment.base import DeploymentProvider
from backend.services.deployment.capabilities import CATALOG, PROVIDER_ORDER
from backend.services.deployment.cloudflare import CloudflarePagesProvider
from backend.services.deployment.github_pages import GitHubPagesProvider
from backend.services.deployment.netlify import NetlifyProvider
from backend.services.deployment.render import RenderProvider
from backend.services.deployment.vercel import VercelProvider


def _stored_github_token(user_id: int | None) -> str | None:
    """Look up a user's GitHub token for status/log/destroy calls made outside a request."""
    from backend.services.github import get_token

    if user_id is None:
        return None
    with SessionLocal() as db:
        return get_token(db, user_id)


_PROVIDERS: dict[str, DeploymentProvider] = {
    "render": RenderProvider(),
    "vercel": VercelProvider(),
    "netlify": NetlifyProvider(),
    "github_pages": GitHubPagesProvider(_stored_github_token),
    "cloudflare_pages": CloudflarePagesProvider(_stored_github_token),
}


def get_provider(key: str) -> DeploymentProvider:
    try:
        return _PROVIDERS[key]
    except KeyError:
        raise KeyError(f"Unknown provider '{key}'") from None


def all_providers() -> list[DeploymentProvider]:
    return [_PROVIDERS[k] for k in PROVIDER_ORDER]


__all__ = ["CATALOG", "PROVIDER_ORDER", "get_provider", "all_providers"]
