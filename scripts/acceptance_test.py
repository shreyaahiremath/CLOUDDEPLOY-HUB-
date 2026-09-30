"""Real provider acceptance test. Deploys the sample projects to the REAL providers configured in
backend/.env, waits for each provider to report the deployment live, reads the provider-returned
URL, checks it over HTTP, then destroys the resource (unless --keep).

A provider only counts as working when this prints PASS for it. Missing credentials print
"Provider Not Configured" and never PASS.

Usage (from the repository root):
    backend/.venv/Scripts/python scripts/acceptance_test.py --providers vercel netlify
    backend/.venv/Scripts/python scripts/acceptance_test.py --providers render github_pages cloudflare_pages \
        --static-repo you/clouddeploy-sample-project --api-repo you/clouddeploy-sample-fastapi

Render, GitHub Pages and Cloudflare Pages deploy from GitHub: push samples/sample-project and
samples/sample-fastapi to your own repositories first and set GITHUB_TOKEN (repo + workflow scopes).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CDH_DATA_DIR", str(ROOT / "backend" / "data" / "acceptance"))

from backend.config import settings  # noqa: E402
from backend.models import Deployment, Project  # noqa: E402
from backend.services.deployment import get_provider  # noqa: E402
from backend.services.deployment.base import PHASE_FAILED, PHASE_LIVE, DeployConfig, DeployContext, DeployError  # noqa: E402
from backend.services.deployment.health import check_with_retries, paths_for  # noqa: E402
from backend.services.github.client import GitHubClient  # noqa: E402
from backend.services.project_analyzer import CallbackFileSource, LocalFileSource, analyze  # noqa: E402

SAMPLES = ROOT / "samples"


async def build_project(kind: str, repo: str | None, gh: GitHubClient) -> Project:
    if repo:
        owner, name = repo.split("/", 1)
        info = await gh.get_repo(owner, name)
        branch = info["default_branch"]
        paths = await gh.get_tree(owner, name, branch)
        analysis = await analyze(CallbackFileSource(paths, lambda p: gh.get_file_text(owner, name, p, branch)))
        project = Project(id=0, user_id=0, name=f"cdh-accept-{kind}", source_type="github", github_owner=owner,
                          github_repo=name, repo_private=info["private"], branch=branch, root_dir="")
    else:
        src = SAMPLES / ("sample-project" if kind == "static" else "sample-fastapi")
        analysis = await analyze(LocalFileSource(src))
        project = Project(id=0, user_id=0, name=f"cdh-accept-{kind}", source_type="upload", workspace_path=str(src), root_dir="")
    project.analysis_json = json.dumps(analysis)
    return project


async def run_one(key: str, project: Project, gh: GitHubClient, keep: bool) -> tuple[str, str]:
    provider = get_provider(key)
    missing = provider.missing_credentials()
    if missing:
        return "SKIP", f"Provider Not Configured (missing {', '.join(missing)})"
    stamp = datetime.now(timezone.utc).strftime("%m%d%H%M")
    ctx = DeployContext(project, project.analysis, DeployConfig(name=f"cdh-accept-{stamp}"), gh, None,
                        lambda m: print(f"    · {m}"))
    errors, warnings = provider.validate(ctx)
    for w in warnings:
        print(f"    ! {w}")
    if errors:
        return "FAIL", "validation: " + " ".join(errors)
    try:
        handle = await provider.deploy(ctx)
    except DeployError as exc:
        return "FAIL", f"{exc.reason} | fix: {exc.suggested_fix}"
    dep = Deployment(id=0, user_id=0, project_id=0, project_name=project.name, provider=key, source_type=project.source_type,
                     deployment_id=handle.deployment_id, provider_resource_id=handle.resource_id,
                     meta_json=json.dumps(handle.meta), created_at=datetime.now(timezone.utc))
    print(f"    deployment_id={handle.deployment_id} resource={handle.resource_id}")
    started, last = time.monotonic(), None
    try:
        while time.monotonic() - started < 25 * 60:
            st = await provider.get_status(dep)
            if st.meta:
                dep.set_meta(**st.meta)
            if st.deployment_id:
                dep.deployment_id = st.deployment_id
            if st.raw != last:
                print(f"    status: {st.raw}")
                last = st.raw
            if st.phase == PHASE_FAILED:
                logs = await provider.get_logs(dep)
                tail = "\n".join(line.message for line in logs[-10:])
                return "FAIL", f"{st.error}\n{tail}"
            if st.phase == PHASE_LIVE:
                break
            await asyncio.sleep(6)
        else:
            return "FAIL", "timed out waiting for the provider"
        url = (await provider.get_outputs(dep)).get("public_url")
        if not url:
            return "FAIL", "provider returned no public URL"
        health = await check_with_retries(url, paths_for(project.analysis.get("app_type"), None))
        logs = await provider.get_logs(dep)
        print(f"    url: {url}\n    health: {health.detail}\n    provider log lines: {len(logs)}")
        return ("PASS" if health.healthy else "FAIL"), f"{url} ({health.detail}) deployment_id={dep.deployment_id}"
    finally:
        if not keep:
            try:
                await provider.destroy(dep)
                print("    destroyed")
            except Exception as exc:  # noqa: BLE001
                print(f"    destroy failed: {exc}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", nargs="+", default=["vercel", "netlify", "render", "github_pages", "cloudflare_pages"])
    ap.add_argument("--static-repo", help="owner/repo containing samples/sample-project (public, for Pages)")
    ap.add_argument("--api-repo", help="owner/repo containing samples/sample-fastapi (for Render)")
    ap.add_argument("--keep", action="store_true", help="do not destroy resources afterwards")
    args = ap.parse_args()

    results = []
    async with GitHubClient(settings.github_token or None) as gh:
        # the provider registry reads GitHub tokens per user; point it at GITHUB_TOKEN for this script
        from backend.services import deployment as registry
        for p in ("github_pages", "cloudflare_pages"):
            registry._PROVIDERS[p]._token_getter = lambda _uid: settings.github_token or None
        for key in args.providers:
            print(f"\n== {key} ==")
            if key == "render":
                if not args.api_repo:
                    results.append((key, "SKIP", "needs --api-repo (Render deploys from GitHub)"))
                    continue
                project = await build_project("api", args.api_repo, gh)
            elif key in ("github_pages", "cloudflare_pages"):
                if not args.static_repo:
                    results.append((key, "SKIP", "needs --static-repo (deploys from GitHub)"))
                    continue
                project = await build_project("static", args.static_repo, gh)
            else:
                project = await build_project("static", None, gh)
            status, detail = await run_one(key, project, gh, args.keep)
            results.append((key, status, detail))

    print("\n==== Acceptance results ====")
    for key, status, detail in results:
        print(f"{status:5} {key:17} {detail}")
    return 0 if all(s != "FAIL" for _, s, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
