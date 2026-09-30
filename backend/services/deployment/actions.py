"""Shared pieces for providers that build inside the user's own GitHub Actions
(GitHub Pages, Cloudflare Pages): workflow generation and run tracking."""
from __future__ import annotations

import re
from datetime import datetime

from backend.models import Deployment
from backend.services.deployment.base import (
    PHASE_BUILDING,
    PHASE_DEPLOYING,
    PHASE_FAILED,
    PHASE_LIVE,
    PHASE_QUEUED,
    DeployContext,
    LogLine,
    ProviderStatus,
)
from backend.services.github.client import GitHubClient

VITE_KEYS = {"vite-react", "vite-vue", "vite-svelte", "vite"}
SPA_KEYS = VITE_KEYS | {"create-react-app", "vue", "angular"}
_LOG_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}T[\d:.]+Z)\s?(.*)$")


def _q(value: str) -> str:
    """Single-quote a value for YAML/shell."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def build_steps(ctx: DeployContext, *, base_path: str | None = None) -> tuple[list[str], str]:
    """Return (YAML step lines indented for a job's `steps:`, output directory path)."""
    a = ctx.analysis
    root = ctx.root_dir.strip("/")
    workdir = root or "."
    needs_build = bool(ctx.pick("build_command")) and a.get("needs_build", True)
    steps = ["      - uses: actions/checkout@v4"]

    if not needs_build:
        src = f"{workdir}/{(ctx.pick('output_dir') or '.').strip('/')}".replace("/./", "/").rstrip("/.") or "."
        steps += [
            "      - name: Collect static files",
            "        run: |",
            '          mkdir -p "$RUNNER_TEMP/site"',
            f'          rsync -a --exclude .git --exclude .github {_q(src + "/")} "$RUNNER_TEMP/site/"',
        ]
        return steps, "${{ runner.temp }}/site"

    install = ctx.pick("install_command") or "npm install"
    build = ctx.pick("build_command")
    env: dict[str, str] = {}
    key = a.get("framework_key")
    if base_path and base_path != "/":
        if key in VITE_KEYS and not ctx.config.build_command:
            sep = " -- " if (a.get("package_manager") or "npm") == "npm" else " "
            build = f"{build}{sep}--base={base_path}"
        elif key == "create-react-app":
            env["PUBLIC_URL"] = base_path.rstrip("/")
    steps += [
        "      - uses: actions/setup-node@v4",
        "        with:",
        "          node-version: 20",
    ]
    if a.get("package_manager") == "pnpm":
        steps.insert(1, "      - uses: pnpm/action-setup@v4")
    steps += [
        "      - name: Install dependencies",
        f"        working-directory: {_q(workdir)}",
        f"        run: {install}",
        "      - name: Build",
        f"        working-directory: {_q(workdir)}",
        f"        run: {build}",
    ]
    if env:
        steps.append("        env:")
        steps += [f"          {k}: {_q(v)}" for k, v in env.items()]
    out = f"{workdir}/{(ctx.pick('output_dir') or 'dist').strip('/')}".removeprefix("./")
    if key in SPA_KEYS:
        steps += [
            "      - name: SPA fallback page",
            f"        run: cp {_q(out + '/index.html')} {_q(out + '/404.html')} || true",
        ]
    return steps, out


class ActionsRunTracker:
    """Status + logs for a workflow_dispatch run recorded in deployment.meta."""

    def __init__(self, client_factory):
        self._client_factory = client_factory  # (deployment) -> GitHubClient

    async def find_run(self, gh: GitHubClient, deployment: Deployment) -> dict | None:
        meta = deployment.meta
        if meta.get("run_id"):
            return await gh.get_run(meta["owner"], meta["repo"], meta["run_id"])
        since = datetime.fromisoformat(meta["dispatched_at"])
        return await gh.find_run(meta["owner"], meta["repo"], meta["workflow_file"], meta["branch"], since)

    async def status(self, deployment: Deployment) -> ProviderStatus:
        async with self._client_factory(deployment) as gh:
            run = await self.find_run(gh, deployment)
            if run is None:
                return ProviderStatus(PHASE_QUEUED, "waiting_for_workflow_run")
            meta = {"run_id": run["id"], "run_url": run.get("html_url")}
            status, conclusion = run.get("status"), run.get("conclusion")
            if status != "completed":
                phase = PHASE_QUEUED if status in ("queued", "waiting", "pending", "requested") else PHASE_BUILDING
                if phase == PHASE_BUILDING:
                    jobs = await gh.get_run_jobs(deployment.meta["owner"], deployment.meta["repo"], run["id"])
                    if any(j["name"].lower().startswith("deploy") and j.get("status") == "in_progress" for j in jobs):
                        phase = PHASE_DEPLOYING
                return ProviderStatus(phase, f"actions:{status}", meta=meta)
            if conclusion == "success":
                return ProviderStatus(PHASE_LIVE, "actions:success", meta=meta)
            jobs = await gh.get_run_jobs(deployment.meta["owner"], deployment.meta["repo"], run["id"])
            failed = [
                f"{j['name']} → {s['name']}"
                for j in jobs for s in j.get("steps", []) if s.get("conclusion") == "failure"
            ]
            reason = f"GitHub Actions run {conclusion}" + (f" at step: {', '.join(failed)}" if failed else "")
            return ProviderStatus(PHASE_FAILED, f"actions:{conclusion}", error=reason, meta=meta)

    async def logs(self, deployment: Deployment, source: str) -> list[LogLine]:
        meta = deployment.meta
        if not meta.get("run_id"):
            return []
        lines: list[LogLine] = []
        async with self._client_factory(deployment) as gh:
            for job in await gh.get_run_jobs(meta["owner"], meta["repo"], meta["run_id"]):
                text = await gh.get_job_logs(meta["owner"], meta["repo"], job["id"])
                for raw in text.splitlines()[-400:]:
                    m = _LOG_LINE.match(raw.lstrip("﻿"))
                    ts, msg = (m.group(1), m.group(2)) if m else (None, raw)
                    if msg.strip():
                        level = "error" if "##[error]" in msg else "info"
                        lines.append(LogLine(ts, msg.replace("##[error]", "").replace("##[group]", "▸ "), f"{source}:{job['name']}", level))
        return lines
