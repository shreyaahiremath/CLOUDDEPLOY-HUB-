"""Upload, validation, analyzer, Docker and framework detection."""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path

from backend.services.docker import generate_dockerfile, validate_dockerfile
from backend.services.project_analyzer import LocalFileSource, analyze
from backend.services.workspace.validation import normalize_path, validate_files

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
LIMITS = dict(max_total=10_000_000, max_file=1_000_000, max_files=100)


def run(coro):
    return asyncio.run(coro)


def analyze_files(tmp_path: Path, files: dict[str, str]) -> dict:
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return run(analyze(LocalFileSource(tmp_path)))


# ----- validation --------------------------------------------------------------------------
def test_path_traversal_and_absolute_paths_are_rejected():
    assert normalize_path("../etc/passwd") is None
    assert normalize_path("a/../../b") is None
    assert normalize_path("/etc/passwd") is None
    assert normalize_path("C:\\Windows\\system32") is None
    assert normalize_path("src\\app.py") == "src/app.py"
    assert normalize_path("./src/./app.py") == "src/app.py"


def test_env_secrets_and_executables_are_excluded():
    report, files = validate_files(
        [
            ("app/index.html", b"<h1>hi</h1>"),
            ("app/.env", b"SECRET=1"),
            ("app/.env.example", b"SECRET="),
            ("app/deploy.pem", b"x"),
            ("app/tool.exe", b"MZ"),
            ("app/config.js", b"const k = 'ghp_" + b"a" * 36 + b"'"),
            ("app/node_modules/x/index.js", b""),
            ("../escape.txt", b"x"),
        ],
        **LIMITS,
    )
    assert set(files) == {"index.html", ".env.example"}
    categories = {r.category for r in report.rejected}
    assert {"env", "secret", "dangerous", "invalid_path"} <= categories
    assert report.skipped_count == 1


def test_size_limits():
    report, _ = validate_files([("big.bin", b"x" * 2_000_000), ("a.txt", b"ok")], **LIMITS)
    assert any(r.category == "too_large" for r in report.rejected)
    report, _ = validate_files([("a.txt", b"x" * 900_000)] * 1 + [(f"f{i}.txt", b"x" * 900_000) for i in range(12)], **LIMITS)
    assert report.errors  # > max_total


def test_upload_folder_endpoint_creates_project_and_analyzes(client):
    files = [
        ("files", ("index.html", b"<!doctype html><title>x</title>", "text/html")),
        ("files", ("package.json", b'{"name":"site"}', "application/json")),
        ("files", (".env", b"TOKEN=abc", "text/plain")),
    ]
    data = {"name": "my-site", "paths": ["my-site/index.html", "my-site/package.json", "my-site/.env"]}
    resp = client.post("/api/projects/upload", data=data, files=files)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["analysis"]["app_type"] == "Static Frontend"
    assert body["upload_report"]["accepted_count"] == 2
    assert body["upload_report"]["rejected"][0]["category"] == "env"


def test_upload_zip_endpoint(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in (SAMPLES / "sample-fastapi").rglob("*"):
            if p.is_file():
                zf.write(p, f"sample-fastapi/{p.relative_to(SAMPLES / 'sample-fastapi').as_posix()}")
    resp = client.post("/api/projects/upload", files={"files": ("sample-fastapi.zip", buf.getvalue(), "application/zip")})
    assert resp.status_code == 201, resp.text
    a = resp.json()["analysis"]
    assert a["framework"] == "FastAPI" and a["python_entry"] == "app.main:app" and a["has_dockerfile"]


def test_upload_rejects_empty_result(client):
    resp = client.post("/api/projects/upload", files={"files": (".env", b"A=1", "text/plain")}, data={"paths": [".env"]})
    assert resp.status_code == 400


# ----- analyzer ----------------------------------------------------------------------------
def test_analyzer_sample_projects():
    static = run(analyze(LocalFileSource(SAMPLES / "sample-project")))
    assert static["framework_key"] == "static" and static["app_type"] == "Static Frontend"
    api = run(analyze(LocalFileSource(SAMPLES / "sample-fastapi")))
    assert api["framework_key"] == "fastapi" and api["app_type"] == "Backend API"
    assert api["start_command"] == "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    assert "Dockerfile" in api["build_files"] and api["dockerfile_issues"] == []


def test_detects_vite_react(tmp_path):
    a = analyze_files(tmp_path, {
        "package.json": json.dumps({"scripts": {"build": "tsc -b && vite build"}, "dependencies": {"react": "19"}, "devDependencies": {"vite": "7", "typescript": "5"}}),
        "package-lock.json": "{}", "index.html": "<div id=root></div>", "vite.config.ts": "",
    })
    assert a["framework"] == "React (Vite)" and a["app_type"] == "Frontend"
    assert a["build_command"] == "npm run build" and a["output_dir"] == "dist" and a["install_command"] == "npm ci"
    assert a["language"] == "TypeScript"


def test_detects_nextjs_ssr_and_static_export(tmp_path):
    pkg = json.dumps({"scripts": {"build": "next build", "start": "next start"}, "dependencies": {"next": "15", "react": "19"}})
    a = analyze_files(tmp_path, {"package.json": pkg, "next.config.js": "module.exports = {}"})
    assert a["framework_key"] == "nextjs" and a["app_type"] == "Full Stack"
    (tmp_path / "next.config.js").write_text("module.exports = { output: 'export' }")
    b = run(analyze(LocalFileSource(tmp_path)))
    assert b["app_type"] == "Static Frontend" and b["output_dir"] == "out"


def test_detects_express_flask_django(tmp_path):
    a = analyze_files(tmp_path / "e", {"package.json": json.dumps({"scripts": {"start": "node server.js"}, "dependencies": {"express": "4"}}), "server.js": ""})
    assert a["framework"] == "Express" and a["app_type"] == "Backend API" and a["start_command"] == "npm run start"
    f = analyze_files(tmp_path / "f", {"requirements.txt": "flask\ngunicorn", "app.py": "from flask import Flask\napp = Flask(__name__)\n"})
    assert f["framework"] == "Flask" and f["python_entry"] == "app:app"
    d = analyze_files(tmp_path / "d", {"requirements.txt": "Django>=5", "manage.py": "", "mysite/wsgi.py": ""})
    assert d["framework"] == "Django" and d["python_entry"] == "mysite.wsgi:application"


def test_root_dir_and_subproject_hint(tmp_path):
    a = analyze_files(tmp_path, {"frontend/package.json": json.dumps({"dependencies": {"vite": "7", "vue": "3"}, "scripts": {"build": "vite build"}}), "README.md": ""})
    assert "frontend" in a["subprojects"]
    b = run(analyze(LocalFileSource(tmp_path), "frontend"))
    assert b["framework"] == "Vue (Vite)"


def test_dockerfile_validation_and_generation():
    assert validate_dockerfile("") == ["Dockerfile is empty."]
    issues = validate_dockerfile("FROM python:3.11\nENV API_KEY=abc\n")
    assert any("CMD" in i for i in issues) and any("secret" in i for i in issues)
    generated = generate_dockerfile({"framework_key": "fastapi", "python_entry": "app.main:app"})
    assert generated.startswith("FROM python:3.11-slim") and "uvicorn app.main:app" in generated
    assert validate_dockerfile(generated) == []
    assert generate_dockerfile({"framework_key": "static"}) is None


def test_upload_survives_ephemeral_disk_wipe(client):
    """Render free instances lose their disk on restart; the DB copy restores the workspace."""
    from backend.services import workspace

    files = [("files", ("index.html", b"<!doctype html><h1>hi</h1>", "text/html"))]
    project = client.post("/api/projects/upload", data={"name": "site", "paths": ["site/index.html"]}, files=files).json()
    workspace.delete_workspace(project["id"])
    resp = client.post(f"/api/projects/{project['id']}/analyze")
    assert resp.status_code == 200 and resp.json()["analysis"]["framework_key"] == "static"
    preview = client.get(f"/api/projects/{project['id']}/github/preview").json()
    assert [f["path"] for f in preview["files"]] == [".gitignore", "index.html"]
