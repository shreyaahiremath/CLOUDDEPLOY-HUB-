"""Resolve a project's source files for providers that upload files (Vercel, Netlify)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from backend.services import workspace

if TYPE_CHECKING:
    from backend.services.deployment.base import DeployContext


async def snapshot(ctx: DeployContext) -> dict[str, bytes]:
    project = ctx.project
    if project.source_type == "github" and project.repository:
        ref = ctx.config.branch or project.branch or "HEAD"
        ctx.log(f"Downloading {project.repository}@{ref} from GitHub")
        data = await ctx.github.download_tarball(project.github_owner, project.github_repo, ref)
        files, report = workspace.extract_github_tarball(data)
        if report.rejected:
            ctx.log(f"Excluded {len(report.rejected)} file(s) that failed validation (secrets/.env/executables)")
    elif project.source_type == "upload":
        from sqlalchemy.orm import object_session

        root = workspace.ensure_workspace(object_session(project), project)
        if root is None:
            raise FileNotFoundError("The uploaded files for this project are no longer available. Upload it again.")
        files = workspace.read_tree(root)
    else:
        raise FileNotFoundError("This project has no source files. Upload it again or connect a repository.")
    root = ctx.root_dir.strip("/")
    if root:
        prefix = f"{root}/"
        files = {k[len(prefix):]: v for k, v in files.items() if k.startswith(prefix)}
        if not files:
            raise FileNotFoundError(f"Root directory '{root}' has no files")
    return files
