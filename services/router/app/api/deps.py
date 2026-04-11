"""Authentication dependency — API key validation."""

import os
import sqlite3

from fastapi import Header, HTTPException, status

from app.config import settings

# Same as keys.py: /app/db matches docker-compose volume mount
DB_DIR = os.environ.get("ROUTER_DB_DIR", "/app/db")
DB_PATH = os.path.join(DB_DIR, "router.db")


def _get_valid_keys():
    """Get set of valid API keys from SQLite + fallback to config."""
    keys = set()
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute(
                "SELECT key_value FROM api_keys WHERE is_active = 1"
            ).fetchall()
            conn.close()
            for row in rows:
                keys.add(row[0])
        except Exception:
            pass
    # Always include the config key as fallback/admin key
    keys.add(settings.API_KEY)
    return keys


async def verify_api_key(authorization: str = Header(default=None)) -> None:
    """Validate Bearer token matches a stored API key."""
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    valid_keys = _get_valid_keys()
    if scheme.lower() != "bearer" or token not in valid_keys:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


async def verify_admin_key(authorization: str = Header(default=None)) -> None:
    """Validate Bearer token matches the config admin key (not a user key)."""
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != settings.API_KEY:
        raise HTTPException(status_code=status.HTTP_403_UNAUTHORIZED, detail="Admin key required")
