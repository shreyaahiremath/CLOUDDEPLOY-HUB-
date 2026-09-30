"""Encryption for tokens stored at rest (the GitHub OAuth token)."""
from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

from backend.config import settings

_KEY_FILE = settings.data_dir / "secret.key"


def _load_key() -> bytes:
    if settings.secret_key:
        return base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    return key


_fernet = Fernet(_load_key())


def encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    try:
        return _fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return None


def seal_env(config: dict) -> dict:
    """Encrypt environment-variable values before a deployment config is stored."""
    env = config.get("env_vars") or {}
    if not env or config.get("env_sealed"):
        return config
    return {**config, "env_vars": {k: encrypt(v) for k, v in env.items()}, "env_sealed": True}


def open_env(config: dict) -> dict:
    if not config.get("env_sealed"):
        return config
    env = {k: decrypt(v) or "" for k, v in (config.get("env_vars") or {}).items()}
    return {k: v for k, v in {**config, "env_vars": env}.items() if k != "env_sealed"}


def public_config(config: dict) -> dict:
    """Config safe to return to the browser: variable names only, never values."""
    out = {k: v for k, v in config.items() if k not in ("env_vars", "env_sealed")}
    out["env_var_names"] = sorted((config.get("env_vars") or {}).keys())
    return out


def new_state() -> str:
    return secrets.token_urlsafe(32)
