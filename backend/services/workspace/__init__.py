"""Temporary project workspaces: uploaded projects and GitHub snapshots live here."""
from __future__ import annotations

import io
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

from backend.config import settings
from backend.services import supabase_store
from backend.services.workspace.validation import ValidationReport, normalize_path, validate_files


class WorkspaceError(Exception):
    pass


def validate(files: list[tuple[str, bytes]]) -> tuple[ValidationReport, dict[str, bytes]]:
    return validate_files(
        files,
        max_total=settings.max_upload_bytes,
        max_file=settings.max_file_bytes,
        max_files=settings.max_files,
    )


def expand_zip(data: bytes) -> list[tuple[str, bytes]]:
    """Read a .zip upload into (path, bytes) pairs without extracting to disk. Zip-bomb guarded."""
    out: list[tuple[str, bytes]] = []
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.file_size > settings.max_file_bytes * 4:
                    out.append((info.filename, b"\x00" * (settings.max_file_bytes + 1)))
                    continue
                total += info.file_size
                if total > settings.max_upload_bytes * 4:
                    raise WorkspaceError("Archive expands beyond the upload limit")
                out.append((info.filename, zf.read(info)))
    except zipfile.BadZipFile as exc:
        raise WorkspaceError("The uploaded .zip file is not a valid archive") from exc
    return out


def write_workspace(project_id: int, files: dict[str, bytes]) -> Path:
    root = settings.workspaces_dir / str(project_id) / "src"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    base = root.resolve()
    for rel, data in files.items():
        target = (root / rel).resolve()
        if base not in target.parents:
            raise WorkspaceError(f"Refusing to write outside the workspace: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def ensure_workspace(db, project) -> Path | None:
    """Return the project's workspace dir, restoring it from the database copy if the disk was wiped."""
    from backend.models import ProjectSource

    if project.workspace_path:
        existing = Path(project.workspace_path)
        if existing.is_dir() and any(existing.iterdir()):
            return existing
    if project.source_type != "upload" or db is None:
        return None
    source = db.get(ProjectSource, project.id)
    archive = source.archive if source is not None else supabase_store.store.get_source(project.id)
    if archive is None:
        return None
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        for info in zf.infolist():
            rel = normalize_path(info.filename)
            if rel and not info.is_dir():
                files[rel] = zf.read(info)
    root = write_workspace(project.id, files)
    if project.workspace_path != str(root):
        project.workspace_path = str(root)
        db.commit()
    return root


def delete_workspace(project_id: int, *, stored_copy: bool = False) -> None:
    shutil.rmtree(settings.workspaces_dir / str(project_id), ignore_errors=True)
    if stored_copy:
        supabase_store.store.delete_source(project_id)


def read_tree(root: Path, sub_dir: str = "") -> dict[str, bytes]:
    base = root / sub_dir if sub_dir else root
    if not base.is_dir():
        raise WorkspaceError(f"Root directory '{sub_dir}' does not exist in the project")
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


def list_tree(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for p in sorted(root.rglob("*")) if p.is_file()]


def extract_github_tarball(data: bytes) -> tuple[dict[str, bytes], ValidationReport]:
    """Safely read a GitHub tarball (top folder 'owner-repo-sha/') into validated files."""
    pairs: list[tuple[str, bytes]] = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():  # skip symlinks, devices, dirs
                continue
            parts = member.name.split("/", 1)
            if len(parts) != 2 or normalize_path(parts[1]) is None:
                continue
            fh = tar.extractfile(member)
            if fh is not None:
                pairs.append((parts[1], fh.read()))
    report, files = validate(pairs)
    return files, report


def make_zip(files: dict[str, bytes], extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, data in {**files, **(extra or {})}.items():
            zf.writestr(rel, data)
    return buf.getvalue()


def scratch_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="cdh-", dir=settings.data_dir))
