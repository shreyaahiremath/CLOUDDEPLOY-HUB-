"""FastAPI integration-test project for Git2Live."""
import os
import platform
from datetime import datetime, timezone

from fastapi import FastAPI

app = FastAPI(title="Git2Live sample API")


@app.get("/")
def root() -> dict:
    return {"message": "Hello from the Git2Live sample FastAPI app", "python": platform.python_version()}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat(), "port": os.environ.get("PORT")}
