"""Validation for user-supplied project files.

Git2Live never executes uploaded code locally. Builds always run on the provider (or in the
user's own GitHub Actions). This module only decides which files are safe to keep and publish.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

# Directories that are build artifacts / dependency caches: skipped silently (not errors).
SKIPPED_DIRS = {
    "node_modules", ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env", ".mypy_cache",
    ".pytest_cache", ".next", ".nuxt", ".turbo", ".cache", ".parcel-cache", ".vercel", ".netlify",
    ".idea", ".vscode", ".DS_Store", "coverage", ".tox", ".gradle", "target",
}

# Files that must never be uploaded or published.
SECRET_FILENAMES = {
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc", ".git-credentials",
    "credentials.json", "service-account.json", "serviceaccount.json", ".htpasswd",
}
SECRET_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx", ".ppk"}
ENV_TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")

DANGEROUS_EXTENSIONS = {
    ".exe", ".dll", ".msi", ".bat", ".cmd", ".com", ".scr", ".vbs", ".ps1", ".psm1", ".cpl",
    ".sys", ".apk", ".dmg", ".pkg", ".deb", ".rpm", ".app",
}

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Stripe live key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("OpenAI/Anthropic key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{32,}\b")),
]

_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass
class FileDecision:
    path: str
    size: int
    accepted: bool
    reason: str | None = None
    category: str | None = None  # skipped | secret | env | dangerous | too_large | invalid_path


@dataclass
class ValidationReport:
    accepted: list[FileDecision] = field(default_factory=list)
    rejected: list[FileDecision] = field(default_factory=list)
    skipped_count: int = 0
    total_bytes: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "accepted_count": len(self.accepted),
            "total_bytes": self.total_bytes,
            "skipped_count": self.skipped_count,
            "rejected": [
                {"path": d.path, "reason": d.reason, "category": d.category} for d in self.rejected
            ],
            "errors": self.errors,
        }


def normalize_path(raw: str) -> str | None:
    """Return a safe, relative POSIX path, or None if the path is unsafe (traversal/absolute)."""
    if not raw or "\x00" in raw:
        return None
    path = raw.replace("\\", "/")
    if path.startswith("/") or _DRIVE.match(path):
        return None
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    normalized = posixpath.normpath("/".join(parts))
    if normalized.startswith("..") or normalized.startswith("/"):
        return None
    return normalized


def strip_common_root(paths: list[str]) -> str:
    """Browsers send folder uploads as 'my-app/src/x.js'. Return the shared top folder, if any."""
    firsts = {p.split("/", 1)[0] for p in paths if "/" in p}
    if len(firsts) == 1 and all("/" in p for p in paths):
        return firsts.pop()
    return ""


def is_env_file(name: str) -> bool:
    lower = name.lower()
    if lower == ".env" or lower.startswith(".env."):
        return not lower.endswith(ENV_TEMPLATE_SUFFIXES)
    return lower.endswith(".env") and not lower.endswith(ENV_TEMPLATE_SUFFIXES)


def classify_path(path: str) -> tuple[str | None, str | None]:
    """Return (category, reason) if the path should not be kept, else (None, None)."""
    parts = path.split("/")
    if any(p in SKIPPED_DIRS for p in parts[:-1]) or parts[-1] in {".DS_Store", "Thumbs.db"}:
        return "skipped", "Dependency/cache folder (rebuilt by the provider)"
    name = parts[-1]
    lower = name.lower()
    ext = posixpath.splitext(lower)[1]
    if is_env_file(name):
        return "env", "Environment file. Set these values as provider environment variables instead"
    if lower in SECRET_FILENAMES or ext in SECRET_EXTENSIONS:
        return "secret", "Credential/key file"
    if ext in DANGEROUS_EXTENSIONS:
        return "dangerous", f"Executable/installer files ({ext}) are not accepted"
    return None, None


def scan_for_secrets(data: bytes) -> str | None:
    if len(data) > 1024 * 1024 or b"\x00" in data[:8000]:
        return None  # binary or very large; not scanned
    text = data.decode("utf-8", errors="ignore")
    for label, pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            line = text.count("\n", 0, match.start()) + 1
            return f"Possible {label} on line {line}. Remove it and use an environment variable"
    return None


def validate_files(
    files: list[tuple[str, bytes]],
    *,
    max_total: int,
    max_file: int,
    max_files: int,
) -> tuple[ValidationReport, dict[str, bytes]]:
    """Validate (path, content) pairs. Returns the report and the accepted files."""
    report = ValidationReport()
    accepted: dict[str, bytes] = {}
    safe_paths = [(normalize_path(p), p, data) for p, data in files]
    root = strip_common_root([p for p, _, _ in safe_paths if p])

    for normalized, original, data in safe_paths:
        if normalized is None:
            report.rejected.append(FileDecision(original, len(data), False, "Unsafe path (traversal or absolute path)", "invalid_path"))
            continue
        path = normalized[len(root) + 1:] if root else normalized
        category, reason = classify_path(path)
        if category == "skipped":
            report.skipped_count += 1
            continue
        if category:
            report.rejected.append(FileDecision(path, len(data), False, reason, category))
            continue
        if len(data) > max_file:
            report.rejected.append(FileDecision(path, len(data), False, f"File larger than {max_file // (1024 * 1024)} MB", "too_large"))
            continue
        secret = scan_for_secrets(data)
        if secret:
            report.rejected.append(FileDecision(path, len(data), False, secret, "secret"))
            continue
        if path in accepted:
            continue
        accepted[path] = data
        report.accepted.append(FileDecision(path, len(data), True))
        report.total_bytes += len(data)

    if len(accepted) > max_files:
        report.errors.append(f"Too many files ({len(accepted)}). The limit is {max_files}.")
    if report.total_bytes > max_total:
        report.errors.append(
            f"Project is {report.total_bytes / 1_048_576:.1f} MB after filtering. The limit is {max_total // 1_048_576} MB."
        )
    if not accepted:
        report.errors.append("No deployable files were found after validation.")
    return report, accepted
