"""Thin GitHub REST API client (https://docs.github.com/en/rest)."""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from urllib.parse import quote

import httpx
from nacl import encoding, public

from backend.services.http import DEFAULT_TIMEOUT, ApiError, request

API = "https://api.github.com"
USERNAME_RULE = "1-39 characters: letters, numbers or single hyphens, not starting or ending with a hyphen"


def valid_username(name: str) -> bool:
    import re

    return bool(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}", name or ""))


class GitHubClient:
    def __init__(self, token: str | None):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(base_url=API, headers=headers, timeout=DEFAULT_TIMEOUT, follow_redirects=True)
        self.authenticated = bool(token)

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def _req(self, method: str, path: str, **kw) -> httpx.Response:
        return await request(self._client, "GitHub", method, path, **kw)

    # ----- identity -------------------------------------------------------------------------
    async def get_user(self) -> tuple[dict, list[str]]:
        resp = await self._req("GET", "/user")
        scopes = [s.strip() for s in resp.headers.get("x-oauth-scopes", "").split(",") if s.strip()]
        return resp.json(), scopes

    async def get_public_user(self, username: str) -> dict:
        return (await self._req("GET", f"/users/{quote(username)}")).json()

    # ----- repositories ---------------------------------------------------------------------
    async def list_repos(self, max_pages: int = 10) -> list[dict]:
        repos: list[dict] = []
        for page in range(1, max_pages + 1):
            resp = await self._req(
                "GET", "/user/repos",
                params={"per_page": 100, "page": page, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
            )
            batch = resp.json()
            repos.extend(batch)
            if len(batch) < 100:
                break
        return repos

    async def list_public_repos(self, username: str) -> list[dict]:
        resp = await self._req("GET", f"/users/{quote(username)}/repos", params={"per_page": 100, "sort": "updated"})
        return resp.json()

    async def get_repo(self, owner: str, repo: str) -> dict:
        return (await self._req("GET", f"/repos/{owner}/{repo}")).json()

    async def list_branches(self, owner: str, repo: str) -> list[dict]:
        return (await self._req("GET", f"/repos/{owner}/{repo}/branches", params={"per_page": 100})).json()

    async def get_tree(self, owner: str, repo: str, ref: str) -> list[str]:
        resp = await self._req("GET", f"/repos/{owner}/{repo}/git/trees/{quote(ref, safe='')}", params={"recursive": "1"})
        return [item["path"] for item in resp.json().get("tree", []) if item.get("type") == "blob"]

    async def get_file_text(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        resp = await self._req(
            "GET", f"/repos/{owner}/{repo}/contents/{quote(path)}", params={"ref": ref},
            headers={"Accept": "application/vnd.github.raw+json"}, ok=(404,),
        )
        if resp.status_code == 404:
            return None
        return resp.content[:256 * 1024].decode("utf-8", errors="ignore")

    async def get_file_sha(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        resp = await self._req("GET", f"/repos/{owner}/{repo}/contents/{quote(path)}", params={"ref": ref}, ok=(404,))
        return None if resp.status_code == 404 else resp.json().get("sha")

    async def download_tarball(self, owner: str, repo: str, ref: str) -> bytes:
        resp = await self._req("GET", f"/repos/{owner}/{repo}/tarball/{quote(ref, safe='')}", timeout=120)
        return resp.content

    async def create_repo(self, name: str, *, private: bool, description: str) -> dict:
        return (
            await self._req(
                "POST", "/user/repos",
                json={"name": name, "private": private, "description": description, "auto_init": True},
            )
        ).json()

    async def push_files(self, owner: str, repo: str, branch: str, files: dict[str, bytes], message: str) -> str:
        """Commit a full snapshot of `files` on top of `branch` using the Git Data API."""
        ref = (await self._req("GET", f"/repos/{owner}/{repo}/git/ref/heads/{quote(branch, safe='')}")).json()
        parent_sha = ref["object"]["sha"]
        sem = asyncio.Semaphore(8)

        async def blob(path: str, data: bytes) -> dict:
            async with sem:
                resp = await self._req(
                    "POST", f"/repos/{owner}/{repo}/git/blobs",
                    json={"content": base64.b64encode(data).decode(), "encoding": "base64"},
                )
            return {"path": path, "mode": "100644", "type": "blob", "sha": resp.json()["sha"]}

        tree_items = await asyncio.gather(*(blob(p, d) for p, d in files.items()))
        tree = (await self._req("POST", f"/repos/{owner}/{repo}/git/trees", json={"tree": tree_items})).json()
        commit = (
            await self._req(
                "POST", f"/repos/{owner}/{repo}/git/commits",
                json={"message": message, "tree": tree["sha"], "parents": [parent_sha]},
            )
        ).json()
        await self._req(
            "PATCH", f"/repos/{owner}/{repo}/git/refs/heads/{quote(branch, safe='')}",
            json={"sha": commit["sha"], "force": False},
        )
        return commit["sha"]

    async def put_file(self, owner: str, repo: str, path: str, content: str, message: str, branch: str) -> dict:
        body = {"message": message, "content": base64.b64encode(content.encode()).decode(), "branch": branch}
        sha = await self.get_file_sha(owner, repo, path, branch)
        if sha:
            body["sha"] = sha
        return (await self._req("PUT", f"/repos/{owner}/{repo}/contents/{quote(path)}", json=body)).json()

    # ----- Actions ----------------------------------------------------------------------------
    async def set_secret(self, owner: str, repo: str, name: str, value: str) -> None:
        key = (await self._req("GET", f"/repos/{owner}/{repo}/actions/secrets/public-key")).json()
        box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
        encrypted = base64.b64encode(box.encrypt(value.encode())).decode()
        await self._req(
            "PUT", f"/repos/{owner}/{repo}/actions/secrets/{name}",
            json={"encrypted_value": encrypted, "key_id": key["key_id"]},
        )

    async def dispatch_workflow(self, owner: str, repo: str, workflow_file: str, ref: str) -> int | None:
        """Trigger a workflow_dispatch run. Newly committed workflows can take a few seconds to register."""
        last: ApiError | None = None
        for attempt in range(8):
            try:
                resp = await self._req(
                    "POST", f"/repos/{owner}/{repo}/actions/workflows/{workflow_file}/dispatches",
                    json={"ref": ref},
                )
                if resp.status_code == 200 and resp.content:
                    return resp.json().get("workflow_run_id")
                return None
            except ApiError as exc:
                if exc.status not in (404, 422):
                    raise
                last = exc
                await asyncio.sleep(3 + attempt * 2)
        assert last is not None
        raise last

    async def find_run(self, owner: str, repo: str, workflow_file: str, branch: str, since: datetime) -> dict | None:
        resp = await self._req(
            "GET", f"/repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs",
            params={"branch": branch, "event": "workflow_dispatch", "per_page": 10},
        )
        for run in resp.json().get("workflow_runs", []):
            created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
            if created.timestamp() >= since.timestamp() - 10:
                return run
        return None

    async def get_run(self, owner: str, repo: str, run_id: int) -> dict:
        return (await self._req("GET", f"/repos/{owner}/{repo}/actions/runs/{run_id}")).json()

    async def get_run_jobs(self, owner: str, repo: str, run_id: int) -> list[dict]:
        return (await self._req("GET", f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs")).json().get("jobs", [])

    async def get_job_logs(self, owner: str, repo: str, job_id: int) -> str:
        resp = await self._req("GET", f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs", ok=(404, 410))
        return "" if resp.status_code in (404, 410) else resp.text

    # ----- Pages ------------------------------------------------------------------------------
    async def enable_pages_workflow(self, owner: str, repo: str) -> dict:
        resp = await self._req("POST", f"/repos/{owner}/{repo}/pages", json={"build_type": "workflow"}, ok=(409,))
        if resp.status_code == 409:  # already enabled: make sure it builds from Actions
            await self._req("PUT", f"/repos/{owner}/{repo}/pages", json={"build_type": "workflow"})
            return await self.get_pages(owner, repo) or {}
        return resp.json()

    async def get_pages(self, owner: str, repo: str) -> dict | None:
        resp = await self._req("GET", f"/repos/{owner}/{repo}/pages", ok=(404,))
        return None if resp.status_code == 404 else resp.json()

    async def delete_pages(self, owner: str, repo: str) -> None:
        await self._req("DELETE", f"/repos/{owner}/{repo}/pages", ok=(404,))
