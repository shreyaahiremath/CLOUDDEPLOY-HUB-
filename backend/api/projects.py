from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import DeploymentStatus, Project, ProjectSource, User
from backend.services.auth import current_user
from backend.schemas import GitHubProjectIn, ProjectUpdateIn, PublishIn, project_out
from backend.services import supabase_store, workspace
from backend.services.deployment import get_provider
from backend.services.deployment.capabilities import CATALOG, evaluate_all
from backend.services.github import client_for, get_connection, get_token
from backend.services.http import ApiError
from backend.services.project_analyzer import CallbackFileSource, LocalFileSource, analyze
from backend.services.workspace.validation import strip_common_root

router = APIRouter(prefix="/api/projects", tags=["projects"])

GITIGNORE = """# Added by CloudDeploy Hub
.env
.env.*
!.env.example
*.pem
*.key
node_modules/
dist/
build/
.next/
out/
__pycache__/
*.pyc
.venv/
venv/
.DS_Store
"""


def _get(db: Session, project_id: int, user: User) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(404, "Project not found.")
    return project


async def _run_analysis(db: Session, project: Project) -> dict:
    if project.source_type == "upload":
        root = workspace.ensure_workspace(db, project)
        if root is None:
            raise HTTPException(410, "The uploaded files for this project are no longer available. Upload it again.")
        source = LocalFileSource(root)
        result = await analyze(source, project.root_dir or "")
    else:
        async with client_for(db, project.user_id) as gh:
            ref = project.branch or "HEAD"
            try:
                paths = await gh.get_tree(project.github_owner, project.github_repo, ref)
            except ApiError as exc:
                raise HTTPException(502, f"Could not read the repository from GitHub: {exc.message}") from exc
            source = CallbackFileSource(
                paths, lambda path: gh.get_file_text(project.github_owner, project.github_repo, path, ref)
            )
            result = await analyze(source, project.root_dir or "")
    project.analysis_json = json.dumps(result)
    db.commit()
    return result


@router.get("")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(Project).filter(Project.user_id == user.id).order_by(Project.updated_at.desc()).all()
    return [project_out(p) for p in rows]


@router.post("/upload", status_code=201)
async def upload_project(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    form = await request.form(max_files=6000, max_fields=6100)
    name = str(form.get("name") or "").strip()
    uploads = form.getlist("files")
    paths = [str(p) for p in form.getlist("paths")]
    if not uploads:
        raise HTTPException(400, "Choose a project folder or a .zip file to upload.")

    pairs: list[tuple[str, bytes]] = []
    try:
        if len(uploads) == 1 and (uploads[0].filename or "").lower().endswith(".zip"):
            pairs = workspace.expand_zip(await uploads[0].read())
            name = name or Path(uploads[0].filename).stem
        else:
            for idx, up in enumerate(uploads):
                rel = paths[idx] if idx < len(paths) and paths[idx] else (up.filename or "")
                pairs.append((rel, await up.read()))
    except workspace.WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        for up in uploads:
            await up.close()

    report, files = workspace.validate(pairs)
    if report.errors:
        raise HTTPException(400, {"message": " ".join(report.errors), "report": report.as_dict()})
    if not name:
        root = strip_common_root([p for p, _ in pairs if p])
        name = root or "my-project"

    project = Project(user_id=user.id, name=name[:120], source_type="upload", upload_report_json=json.dumps(report.as_dict()))
    db.add(project)
    db.commit()
    archive = workspace.make_zip(files)
    db.add(ProjectSource(project_id=project.id, archive=archive, size_bytes=len(archive)))
    try:
        await asyncio.to_thread(supabase_store.store.put_source, project.id, archive)
    except httpx.HTTPError as exc:
        db.rollback()
        db.delete(project)
        db.commit()
        raise HTTPException(502, f"Could not save the upload to Supabase Storage: {exc.__class__.__name__}") from exc
    try:
        project.workspace_path = str(workspace.write_workspace(project.id, files))
    except workspace.WorkspaceError as exc:
        db.delete(project)
        db.commit()
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    await _run_analysis(db, project)
    return project_out(project, detail=True)


@router.post("/github", status_code=201)
async def github_project(body: GitHubProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if not get_token(db, user.id):
        raise HTTPException(401, "Connect GitHub first.")
    try:
        async with client_for(db, user.id) as gh:
            repo = await gh.get_repo(body.owner, body.repo)
    except ApiError as exc:
        raise HTTPException(404 if exc.status == 404 else 502, f"GitHub: {exc.message}") from exc
    project = Project(
        user_id=user.id,
        name=(body.name or repo["name"])[:120],
        source_type="github",
        github_owner=repo["owner"]["login"],
        github_repo=repo["name"],
        repo_private=repo["private"],
        branch=body.branch or repo.get("default_branch") or "main",
    )
    db.add(project)
    db.commit()
    await _run_analysis(db, project)
    return project_out(project, detail=True)


@router.get("/{project_id}")
def get_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return project_out(_get(db, project_id, user), detail=True)


@router.patch("/{project_id}")
async def update_project(project_id: int, body: ProjectUpdateIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    project = _get(db, project_id, user)
    reanalyze = False
    if body.name is not None:
        project.name = body.name
    if body.root_dir is not None and body.root_dir != project.root_dir:
        project.root_dir, reanalyze = body.root_dir, True
    if body.branch is not None and body.branch != project.branch:
        project.branch, reanalyze = body.branch, True
    db.commit()
    if reanalyze:
        await _run_analysis(db, project)
    return project_out(project, detail=True)


@router.post("/{project_id}/analyze")
async def reanalyze(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    project = _get(db, project_id, user)
    await _run_analysis(db, project)
    return project_out(project, detail=True)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    project = _get(db, project_id, user)
    live = [d for d in project.deployments if d.status not in (DeploymentStatus.FAILED, DeploymentStatus.DESTROYED)]
    if live:
        raise HTTPException(
            409, f"This project has {len(live)} deployment(s) that still exist on providers. Destroy them first."
        )
    workspace.delete_workspace(project.id, stored_copy=True)
    db.delete(project)
    db.commit()


@router.get("/{project_id}/compatibility")
def compatibility(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    project = _get(db, project_id, user)
    verdicts = evaluate_all(project.analysis, has_github_repo=bool(project.repository))
    for v in verdicts:
        provider = get_provider(v["provider"])
        v["capability"] = CATALOG[v["provider"]].to_dict()
        missing = provider.missing_credentials()
        if v["provider"] in ("github_pages", "cloudflare_pages") and not get_token(db, user.id):
            missing = [*missing, "GitHub connection"]
        v["configured"] = not missing
        v["missing_credentials"] = missing
    return {"project_id": project.id, "analysis": project.analysis, "providers": verdicts}


# ----- Local project -> GitHub ---------------------------------------------------------------
def _publish_files(db: Session, project: Project) -> tuple[dict[str, bytes], list[str]]:
    root = workspace.ensure_workspace(db, project) if project.source_type == "upload" else None
    if root is None:
        raise HTTPException(400, "Only uploaded projects can be published to GitHub.")
    files = workspace.read_tree(root)
    added = []
    if ".gitignore" not in files:
        files[".gitignore"] = GITIGNORE.encode()
        added.append(".gitignore")
    return files, added


@router.get("/{project_id}/github/preview")
def publish_preview(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    project = _get(db, project_id, user)
    conn = get_connection(db, user.id)
    files, added = _publish_files(db, project)
    report = project.upload_report or {}
    return {
        "files": [{"path": p, "size": len(d), "generated": p in added} for p, d in sorted(files.items())],
        "total_bytes": sum(len(d) for d in files.values()),
        "excluded": report.get("rejected", []),
        "skipped_count": report.get("skipped_count", 0),
        "suggested_name": project.name.lower().replace(" ", "-"),
        "connected_login": conn.verified_login if conn else None,
    }


@router.post("/{project_id}/github/publish")
async def publish(project_id: int, body: PublishIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    project = _get(db, project_id, user)
    if project.repository:
        raise HTTPException(409, f"This project is already linked to {project.repository}.")
    if not get_token(db, user.id):
        raise HTTPException(401, "Connect GitHub first.")
    files, _ = _publish_files(db, project)
    try:
        async with client_for(db, user.id) as gh:
            repo = await gh.create_repo(body.repo_name, private=body.private, description=f"{project.name} (published with CloudDeploy Hub)")
            branch = repo.get("default_branch") or "main"
            sha = await gh.push_files(repo["owner"]["login"], repo["name"], branch, files, "Initial commit from CloudDeploy Hub")
    except ApiError as exc:
        msg = exc.message
        if exc.status == 422 and "name already exists" in str(exc.body).lower():
            msg = f"You already have a repository named '{body.repo_name}'. Choose another name."
        raise HTTPException(400 if exc.status == 422 else 502, f"GitHub: {msg}") from exc
    project.github_owner = repo["owner"]["login"]
    project.github_repo = repo["name"]
    project.repo_private = repo["private"]
    project.branch = branch
    db.commit()
    return {"repository": project.repository, "html_url": repo["html_url"], "commit": sha, "project": project_out(project, detail=True)}
