"""Configuration loading. Reads .env from the project root if present, without
overriding variables already set in the environment."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"

_loaded = False


def load_env() -> None:
    global _loaded
    if _loaded or not ENV_FILE.exists():
        _loaded = True
        return

    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value
    _loaded = True


def mask(secret: str | None) -> str:
    """Render a credential safely for logs and terminal output."""
    if not secret:
        return "<not set>"
    if len(secret) <= 10:
        return f"{secret[:2]}…({len(secret)} chars)"
    return f"{secret[:6]}…{secret[-2:]} ({len(secret)} chars)"
