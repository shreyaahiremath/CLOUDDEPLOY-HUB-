"""Health checks against the real public URL returned by the provider."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

API_TYPES = {"Backend API"}


@dataclass
class HealthResult:
    healthy: bool
    detail: str
    status_code: int | None = None
    checked_url: str | None = None


async def check_once(url: str, paths: list[str], timeout: float = 60.0) -> HealthResult:
    last = HealthResult(False, "Not checked")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": "CloudDeployHub-HealthCheck/1.0"}) as client:
        for path in paths:
            target = url.rstrip("/") + path
            try:
                resp = await client.get(target)
            except httpx.HTTPError as exc:
                last = HealthResult(False, f"GET {path} failed: {exc.__class__.__name__}", None, target)
                continue
            if 200 <= resp.status_code < 300:
                return HealthResult(True, f"GET {path} returned HTTP {resp.status_code}", resp.status_code, target)
            last = HealthResult(False, f"GET {path} returned HTTP {resp.status_code}", resp.status_code, target)
    return last


def paths_for(app_type: str | None, custom: str | None) -> list[str]:
    if custom:
        return [custom if custom.startswith("/") else f"/{custom}"]
    return ["/health", "/"] if app_type in API_TYPES else ["/"]


async def check_with_retries(url: str, paths: list[str], attempts: int = 8, delay: float = 15.0) -> HealthResult:
    """Newly deployed apps can take a while to answer (DNS/CDN propagation, free-tier cold starts)."""
    result = HealthResult(False, "Not checked")
    for attempt in range(attempts):
        result = await check_once(url, paths)
        if result.healthy:
            return result
        if attempt < attempts - 1:
            await asyncio.sleep(delay)
    return result
