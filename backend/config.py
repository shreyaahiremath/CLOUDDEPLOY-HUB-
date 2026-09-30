"""Runtime configuration. All secrets come from environment variables (or backend/.env),
never from the frontend and never from source control."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("CDH_DATA_DIR") or BACKEND_DIR / "data"))
    # Supabase project (durable storage through its HTTPS API; no database password needed)
    supabase_url: str = field(default_factory=lambda: _env("SUPABASE_URL"))
    supabase_secret_key: str = field(
        default_factory=lambda: _env("SUPABASE_SECRET_KEY") or _env("SUPABASE_SERVICE_ROLE_KEY")
    )
    frontend_url: str = field(default_factory=lambda: _env("FRONTEND_URL", "http://localhost:5173"))
    backend_url: str = field(default_factory=lambda: _env("BACKEND_URL", "http://localhost:8000"))
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY"))

    # "Continue with Google" (https://console.cloud.google.com/apis/credentials)
    google_client_id: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_ID"))
    google_client_secret: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_SECRET"))
    # Local development only: enables a no-Google sign-in and the GITHUB_TOKEN fallback. Never enable in production.
    dev_login: bool = field(default_factory=lambda: _env("DEV_LOGIN") in ("1", "true", "yes"))
    session_days: int = 30
    # Extra allowed browser origins (comma separated) and an optional regex, e.g. for Vercel preview URLs.
    cors_origins: str = field(default_factory=lambda: _env("CORS_ORIGINS"))
    cors_origin_regex: str = field(default_factory=lambda: _env("CORS_ORIGIN_REGEX"))

    # GitHub OAuth App (https://github.com/settings/developers)
    github_client_id: str = field(default_factory=lambda: _env("GITHUB_CLIENT_ID"))
    github_client_secret: str = field(default_factory=lambda: _env("GITHUB_CLIENT_SECRET"))
    # Optional developer fallback: a token kept server-side only.
    github_token: str = field(default_factory=lambda: _env("GITHUB_TOKEN"))

    render_api_key: str = field(default_factory=lambda: _env("RENDER_API_KEY"))
    render_owner_id: str = field(default_factory=lambda: _env("RENDER_OWNER_ID"))
    vercel_token: str = field(default_factory=lambda: _env("VERCEL_TOKEN"))
    vercel_team_id: str = field(default_factory=lambda: _env("VERCEL_TEAM_ID"))
    netlify_auth_token: str = field(default_factory=lambda: _env("NETLIFY_AUTH_TOKEN"))
    cloudflare_api_token: str = field(default_factory=lambda: _env("CLOUDFLARE_API_TOKEN"))
    cloudflare_account_id: str = field(default_factory=lambda: _env("CLOUDFLARE_ACCOUNT_ID"))

    # Upload limits
    max_upload_bytes: int = 50 * 1024 * 1024
    max_file_bytes: int = 10 * 1024 * 1024
    max_files: int = 5000

    # Deployment worker
    poll_interval_seconds: float = 5.0
    deployment_timeout_seconds: int = 30 * 60

    @property
    def github_oauth_configured(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def allowed_origins(self) -> list[str]:
        extra = [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]
        return list(dict.fromkeys([self.frontend_url.rstrip("/"), "http://localhost:5173", "http://127.0.0.1:5173", *extra]))

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.workspaces_dir.mkdir(parents=True, exist_ok=True)
