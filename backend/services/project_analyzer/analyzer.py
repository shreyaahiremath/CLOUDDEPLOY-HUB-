"""Static project analysis: reads manifest/config files only. Nothing is executed."""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Protocol

BUILD_FILES = [
    "Dockerfile", "docker-compose.yml", "requirements.txt", "pyproject.toml", "Pipfile", "setup.py",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb",
    "vite.config.js", "vite.config.ts", "vite.config.mjs", "next.config.js", "next.config.mjs",
    "next.config.ts", "nuxt.config.ts", "angular.json", "svelte.config.js", "astro.config.mjs",
    "vue.config.js", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile",
    "composer.json", "Cargo.toml", "Procfile", "manage.py", "netlify.toml", "vercel.json",
    "wrangler.toml", "render.yaml", "index.html",
]
PY_ENTRY_CANDIDATES = [
    "main.py", "app.py", "server.py", "api.py", "wsgi.py", "asgi.py", "app/main.py", "app/app.py",
    "app/__init__.py", "src/main.py", "src/app.py", "api/index.py", "api/main.py",
]
TEXT_LIMIT = 256 * 1024


class FileSource(Protocol):
    paths: list[str]

    async def read(self, path: str) -> str | None: ...


class LocalFileSource:
    def __init__(self, root: Path):
        self.root = root
        self.paths = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]

    async def read(self, path: str) -> str | None:
        target = self.root / path
        if not target.is_file() or target.stat().st_size > TEXT_LIMIT:
            return None
        return target.read_text(encoding="utf-8", errors="ignore")


class CallbackFileSource:
    """File source backed by a remote reader (used for GitHub repositories)."""

    def __init__(self, paths: list[str], reader: Callable[[str], Awaitable[str | None]]):
        self.paths = paths
        self._reader = reader
        self._cache: dict[str, str | None] = {}

    async def read(self, path: str) -> str | None:
        if path not in self._cache:
            self._cache[path] = await self._reader(path)
        return self._cache[path]


@dataclass
class Analysis:
    language: str = "Unknown"
    languages: list[str] = field(default_factory=list)
    framework: str = "Unknown"
    framework_key: str = "unknown"
    app_type: str = "Unknown"  # Static Frontend | Frontend | Serverless | Backend API | Full Stack | Worker | Unknown
    build_files: list[str] = field(default_factory=list)
    has_dockerfile: bool = False
    dockerfile_issues: list[str] = field(default_factory=list)
    package_manager: str | None = None
    install_command: str | None = None
    build_command: str | None = None
    output_dir: str | None = None
    start_command: str | None = None
    python_entry: str | None = None  # "module:variable"
    node_version: str | None = None
    static_export: bool = False
    needs_build: bool = False
    has_index_html: bool = False
    subprojects: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    root_dir: str = ""
    file_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _lang_from_ext(paths: list[str]) -> list[str]:
    ext_map = {
        ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
        ".jsx": "JavaScript", ".mjs": "JavaScript", ".go": "Go", ".java": "Java", ".kt": "Kotlin",
        ".rb": "Ruby", ".php": "PHP", ".rs": "Rust", ".html": "HTML", ".css": "CSS", ".vue": "Vue",
        ".svelte": "Svelte",
    }
    counts: dict[str, int] = {}
    for p in paths:
        lang = ext_map.get(Path(p).suffix.lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])]


def _package_manager(files: set[str]) -> tuple[str, str]:
    if "pnpm-lock.yaml" in files:
        return "pnpm", "pnpm install --frozen-lockfile"
    if "yarn.lock" in files:
        return "yarn", "yarn install --frozen-lockfile"
    if "bun.lockb" in files:
        return "bun", "bun install"
    if "package-lock.json" in files:
        return "npm", "npm ci"
    return "npm", "npm install"


def _run(pm: str, script: str) -> str:
    return f"npm run {script}" if pm == "npm" else f"{pm} run {script}"


PY_FRAMEWORKS = [("fastapi", "FastAPI"), ("django", "Django"), ("flask", "Flask")]
JS_BACKENDS = [
    ("@nestjs/core", "NestJS", "nestjs"), ("express", "Express", "express"), ("fastify", "Fastify", "fastify"),
    ("koa", "Koa", "koa"), ("hono", "Hono", "hono"),
]


async def analyze(source: FileSource, root_dir: str = "") -> dict:
    root_dir = root_dir.strip("/")
    prefix = f"{root_dir}/" if root_dir else ""
    all_paths = [p[len(prefix):] for p in source.paths if p.startswith(prefix)]
    files = set(all_paths)

    async def read(path: str) -> str | None:
        return await source.read(prefix + path)

    a = Analysis(root_dir=root_dir, file_count=len(all_paths))
    a.build_files = [f for f in BUILD_FILES if f in files]
    a.languages = _lang_from_ext(all_paths)
    a.has_index_html = "index.html" in files or "public/index.html" in files
    a.has_dockerfile = "Dockerfile" in files

    if not root_dir:
        tops = {p.split("/", 1)[0] for p in all_paths if "/" in p}
        a.subprojects = sorted(
            t for t in tops if any(f"{t}/{m}" in files for m in ("package.json", "requirements.txt", "pyproject.toml", "go.mod"))
        )

    if a.has_dockerfile:
        a.dockerfile_issues = validate_dockerfile(await read("Dockerfile") or "")

    pkg: dict = {}
    if "package.json" in files:
        try:
            pkg = json.loads(await read("package.json") or "{}")
        except json.JSONDecodeError:
            a.notes.append("package.json is not valid JSON.")
    py_deps = await _python_deps(read, files)

    if pkg:
        _analyze_node(a, pkg, files, await _next_config(read, files))
    if a.framework_key == "unknown" and py_deps is not None:
        await _analyze_python(a, py_deps, files, read)
    if a.framework_key == "unknown":
        _analyze_other(a, files)

    if a.framework_key in ("unknown", "node") and a.has_index_html and not a.needs_build and a.app_type in ("Unknown", "Static Frontend"):
        a.framework, a.framework_key, a.app_type = "Static HTML", "static", "Static Frontend"
        a.language = "HTML/CSS/JS"
        a.output_dir = "." if "index.html" in files else "public"

    if a.language == "Unknown" and a.languages:
        a.language = a.languages[0]
    if a.app_type == "Unknown" and a.subprojects:
        a.notes.append(
            "No app found at the repository root. Set the root directory to one of: " + ", ".join(a.subprojects)
        )
    return a.to_dict()


async def _python_deps(read, files: set[str]) -> set[str] | None:
    deps: set[str] = set()
    found = False
    if "requirements.txt" in files:
        found = True
        for line in (await read("requirements.txt") or "").splitlines():
            name = re.split(r"[<>=!~\[;\s]", line.strip(), maxsplit=1)[0].lower()
            if name and not name.startswith(("#", "-")):
                deps.add(name)
    if "pyproject.toml" in files:
        found = True
        try:
            data = tomllib.loads(await read("pyproject.toml") or "")
            for dep in data.get("project", {}).get("dependencies", []):
                deps.add(re.split(r"[<>=!~\[;\s]", dep, maxsplit=1)[0].lower())
            deps.update(k.lower() for k in data.get("tool", {}).get("poetry", {}).get("dependencies", {}))
        except tomllib.TOMLDecodeError:
            pass
    if "Pipfile" in files:
        found = True
        deps.update(m.lower() for m in re.findall(r"^([A-Za-z0-9_\-]+)\s*=", await read("Pipfile") or "", re.M))
    if not found and any(p.endswith(".py") for p in files):
        return set()
    return deps if found else None


async def _next_config(read, files: set[str]) -> str:
    for name in ("next.config.js", "next.config.mjs", "next.config.ts"):
        if name in files:
            return await read(name) or ""
    return ""


def _analyze_node(a: Analysis, pkg: dict, files: set[str], next_config: str) -> None:
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    scripts: dict = pkg.get("scripts", {}) or {}
    pm, install = _package_manager(files)
    a.package_manager, a.install_command = pm, install
    a.language = "TypeScript" if "typescript" in deps or "tsconfig.json" in files else "JavaScript"
    a.node_version = (pkg.get("engines") or {}).get("node")
    build = _run(pm, "build") if "build" in scripts else None

    def frontend(name: str, key: str, out: str, app_type: str = "Frontend") -> None:
        a.framework, a.framework_key, a.app_type = name, key, app_type
        a.build_command, a.output_dir, a.needs_build = build, out, bool(build)

    if "next" in deps:
        a.framework, a.framework_key = "Next.js", "nextjs"
        a.build_command, a.needs_build = build or "npx next build", True
        a.static_export = bool(re.search(r"output\s*:\s*['\"]export['\"]", next_config))
        a.start_command = _run(pm, "start") if "start" in scripts else "npx next start"
        if a.static_export:
            a.app_type, a.output_dir = "Static Frontend", "out"
            a.notes.append("next.config uses output: 'export', so this builds to static files in out/.")
        else:
            a.app_type, a.output_dir = "Full Stack", ".next"
        return
    if "nuxt" in deps:
        frontend("Nuxt", "nuxt", ".output/public", "Full Stack")
        a.start_command = "node .output/server/index.mjs"
        return
    if "@sveltejs/kit" in deps:
        frontend("SvelteKit", "sveltekit", "build")
        if "@sveltejs/adapter-static" not in deps:
            a.app_type = "Full Stack"
            a.notes.append("SvelteKit without adapter-static needs a server/serverless adapter.")
        return
    if "astro" in deps:
        frontend("Astro", "astro", "dist", "Static Frontend")
        return
    if "@angular/core" in deps:
        name = pkg.get("name", "app")
        frontend("Angular", "angular", f"dist/{name}/browser")
        a.notes.append(f"Angular 17+ outputs to dist/{name}/browser; older versions use dist/{name}.")
        return
    if "react-scripts" in deps:
        frontend("React (Create React App)", "create-react-app", "build")
        return
    if "vite" in deps:
        if "react" in deps:
            frontend("React (Vite)", "vite-react", "dist")
        elif "vue" in deps:
            frontend("Vue (Vite)", "vite-vue", "dist")
        elif "svelte" in deps:
            frontend("Svelte (Vite)", "vite-svelte", "dist")
        else:
            frontend("Vite", "vite", "dist")
        return
    if "@vue/cli-service" in deps:
        frontend("Vue CLI", "vue", "dist")
        return
    for dep, name, key in JS_BACKENDS:
        if dep in deps:
            a.framework, a.framework_key, a.app_type = name, key, "Backend API"
            a.build_command = build
            a.needs_build = bool(build)
            main = pkg.get("main") or next((f for f in ("server.js", "index.js", "app.js", "src/index.js") if f in files), None)
            a.start_command = _run(pm, "start") if "start" in scripts else (f"node {main}" if main else None)
            a.notes.append("Backends must listen on the PORT environment variable (process.env.PORT).")
            if a.has_index_html or any(p.startswith(("client/", "frontend/")) for p in files):
                a.app_type = "Full Stack"
            return
    # package.json without a known framework
    a.framework, a.framework_key = "Node.js", "node"
    if build:
        a.build_command, a.needs_build = build, True
        a.output_dir = "dist" if a.has_index_html else None
        a.app_type = "Frontend" if a.has_index_html else "Unknown"
    elif a.has_index_html:
        a.app_type = "Static Frontend"
    elif "start" in scripts:
        a.start_command, a.app_type = _run(pm, "start"), "Backend API"
    if "netlify/functions" in {str(Path(p).parent) for p in files} or any(p.startswith("api/") for p in files):
        a.notes.append("Serverless functions folder detected (api/ or netlify/functions).")
        if a.app_type in ("Static Frontend", "Frontend"):
            a.app_type = "Serverless"


async def _analyze_python(a: Analysis, deps: set[str], files: set[str], read) -> None:
    a.language = "Python"
    a.install_command = "pip install -r requirements.txt" if "requirements.txt" in files else "pip install ."
    framework = next(((k, n) for k, n in PY_FRAMEWORKS if k in deps), None)
    if framework is None:
        if "manage.py" in files:
            framework = ("django", "Django")
        else:
            for cand in PY_ENTRY_CANDIDATES:
                src = await read(cand) if cand in files else None
                if src and "FastAPI(" in src:
                    framework = ("fastapi", "FastAPI")
                elif src and "Flask(" in src:
                    framework = ("flask", "Flask")
                if framework:
                    break
    if framework is None:
        a.framework, a.framework_key = "Python", "python"
        a.app_type = "Worker" if any(p.endswith(".py") for p in files) else "Unknown"
        a.notes.append("No web framework detected. Workers and scripts cannot be served as websites.")
        return
    key, name = framework
    a.framework, a.framework_key, a.app_type = name, key, "Backend API"
    if key == "django":
        settings_dir = next((p.split("/")[0] for p in files if p.endswith("/wsgi.py")), None)
        a.python_entry = f"{settings_dir}.wsgi:application" if settings_dir else None
        a.start_command = f"gunicorn {settings_dir}.wsgi" if settings_dir else None
        if "gunicorn" not in deps:
            a.notes.append("Add gunicorn to requirements.txt to serve Django in production.")
        if a.python_entry is None:
            a.notes.append("Could not find the Django project's wsgi.py.")
        return
    marker = "FastAPI(" if key == "fastapi" else "Flask("
    for cand in PY_ENTRY_CANDIDATES:
        if cand not in files:
            continue
        src = await read(cand) or ""
        match = re.search(rf"^(\w+)\s*(?::\s*\w+\s*)?=\s*{re.escape(marker)}", src, re.M)
        if match:
            module = cand[:-3].replace("/", ".").removesuffix(".__init__")
            a.python_entry = f"{module}:{match.group(1)}"
            break
    if a.python_entry is None:
        a.notes.append(f"Could not find the {name} app object. Set the start command manually.")
        return
    if key == "fastapi":
        a.start_command = f"uvicorn {a.python_entry} --host 0.0.0.0 --port $PORT"
        if "uvicorn" not in deps:
            a.notes.append("uvicorn is not in requirements.txt. Add it so the provider can start the server.")
    else:
        a.start_command = f"gunicorn {a.python_entry} --bind 0.0.0.0:$PORT"
        if "gunicorn" not in deps:
            a.notes.append("gunicorn is not in requirements.txt. Add it so the provider can start the server.")


def _analyze_other(a: Analysis, files: set[str]) -> None:
    if "go.mod" in files:
        a.language, a.framework, a.framework_key, a.app_type = "Go", "Go", "go", "Backend API"
        a.build_command, a.start_command = "go build -o app .", "./app"
    elif "pom.xml" in files or "build.gradle" in files or "build.gradle.kts" in files:
        a.language, a.framework, a.framework_key, a.app_type = "Java", "Java (Maven/Gradle)", "java", "Backend API"
        a.notes.append("Java apps deploy best with a Dockerfile on Render.")
    elif "Gemfile" in files:
        a.language, a.framework, a.framework_key, a.app_type = "Ruby", "Ruby", "ruby", "Backend API"
    elif "Cargo.toml" in files:
        a.language, a.framework, a.framework_key, a.app_type = "Rust", "Rust", "rust", "Backend API"
    elif a.has_dockerfile:
        a.framework, a.framework_key, a.app_type = "Docker", "docker", "Backend API"


def validate_dockerfile(text: str) -> list[str]:
    issues: list[str] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return ["Dockerfile is empty."]
    if not any(ln.upper().startswith("FROM ") for ln in lines):
        issues.append("Dockerfile has no FROM instruction.")
    if not any(ln.upper().startswith(("CMD", "ENTRYPOINT")) for ln in lines):
        issues.append("Dockerfile has no CMD or ENTRYPOINT, so the container has no process to run.")
    if any(re.search(r"(?i)(password|secret|token|api_key)\s*=", ln) for ln in lines if ln.upper().startswith(("ENV", "ARG"))):
        issues.append("Dockerfile appears to set a secret with ENV/ARG. Use provider environment variables instead.")
    return issues
