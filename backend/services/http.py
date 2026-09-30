"""Shared HTTP helpers for provider APIs."""
from __future__ import annotations

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ApiError(Exception):
    """An error returned by an external API. `message` is the provider's own wording."""

    def __init__(self, service: str, status: int | None, message: str, body: object = None):
        self.service = service
        self.status = status
        self.message = message
        self.body = body
        super().__init__(f"{service} API error{f' {status}' if status else ''}: {message}")


def extract_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return (resp.text or resp.reason_phrase or "").strip()[:500]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("code") or err)
        if isinstance(err, str) and data.get("error_description"):
            return f"{err}: {data['error_description']}"
        errors = data.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            detail = first.get("message") if isinstance(first, dict) else str(first)
            return f"{data.get('message', '')} {detail}".strip()
        for key in ("message", "error", "detail"):
            if data.get(key):
                return str(data[key])
    return str(data)[:500]


async def request(
    client: httpx.AsyncClient, service: str, method: str, url: str, *, ok: tuple[int, ...] = (), **kwargs
) -> httpx.Response:
    try:
        resp = await client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise ApiError(service, None, f"Could not reach {service}: {exc.__class__.__name__}") from exc
    if resp.is_success or resp.status_code in ok:
        return resp
    raise ApiError(service, resp.status_code, extract_message(resp), _safe_json(resp))


def _safe_json(resp: httpx.Response) -> object:
    try:
        return resp.json()
    except ValueError:
        return None
