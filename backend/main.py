"""CloudDeploy Hub API. Run from the repository root:  uvicorn backend.main:app --reload"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import auth, deployments, github, projects, system
from backend.config import PROJECT_ROOT, settings
from backend.database import init_db
from backend.workers import deployment_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    deployment_worker.resume_active()
    yield


app = FastAPI(
    title="CloudDeploy Hub", version="1.0.0", lifespan=lifespan,
    docs_url="/api/swagger", redoc_url=None, openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
for module in (system, auth, github, projects, deployments):
    app.include_router(module.router)

# Serve the built frontend (npm run build) from the same process when it exists.
DIST = PROJECT_ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (DIST / full_path).resolve()
        if full_path and DIST.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
