"""FastAPI integration-test project for CloudDeploy Hub."""
import os
import platform
from datetime import datetime, timezone

from fastapi import FastAPI

app = FastAPI(title="CloudDeploy Hub sample API")


@app.get("/")
def root() -> dict:
    return {"message": "Hello from the CloudDeploy Hub sample FastAPI app", "python": platform.python_version()}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat(), "port": os.environ.get("PORT")}
