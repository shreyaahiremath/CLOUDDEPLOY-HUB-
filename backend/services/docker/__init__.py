"""Dockerfile detection and generation. Generated Dockerfiles are shown to the user before use and
only committed to their repository when they choose Docker build mode."""
from __future__ import annotations

from backend.services.project_analyzer import validate_dockerfile

__all__ = ["generate_dockerfile", "validate_dockerfile"]


def generate_dockerfile(analysis: dict) -> str | None:
    key = analysis.get("framework_key")
    entry = analysis.get("python_entry")
    if key == "fastapi" and entry:
        return (
            "FROM python:3.11-slim\n\n"
            "WORKDIR /app\n\n"
            "COPY requirements.txt .\n\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n\n"
            "COPY . .\n\n"
            "ENV PORT=8000\n"
            "EXPOSE 8000\n\n"
            f'CMD ["sh", "-c", "uvicorn {entry} --host 0.0.0.0 --port ${{PORT}}"]\n'
        )
    if key in ("flask", "django") and entry:
        return (
            "FROM python:3.11-slim\n\n"
            "WORKDIR /app\n\n"
            "COPY requirements.txt .\n\n"
            "RUN pip install --no-cache-dir -r requirements.txt gunicorn\n\n"
            "COPY . .\n\n"
            "ENV PORT=8000\n"
            "EXPOSE 8000\n\n"
            f'CMD ["sh", "-c", "gunicorn {entry} --bind 0.0.0.0:${{PORT}}"]\n'
        )
    if key in ("express", "fastify", "koa", "hono", "nestjs", "node", "nextjs", "nuxt") and analysis.get("start_command"):
        install = analysis.get("install_command") or "npm install"
        if not install.startswith("npm"):
            install = "npm install"
        build = "RUN npm run build\n\n" if analysis.get("build_command") else ""
        return (
            "FROM node:20-alpine\n\n"
            "WORKDIR /app\n\n"
            "COPY package*.json ./\n\n"
            f"RUN {install}\n\n"
            "COPY . .\n\n"
            f"{build}"
            "ENV PORT=3000\n"
            "EXPOSE 3000\n\n"
            f'CMD ["sh", "-c", "{analysis["start_command"]}"]\n'
        )
    return None
