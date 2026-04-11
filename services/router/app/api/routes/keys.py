"""API key management — Phase 4.6 (persistent SQLite)."""

import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import verify_admin_key
from app.config import settings

router = APIRouter()

# Matches docker-compose.yml: ~/ai-paas/data/router_db -> /app/db
DB_DIR = os.environ.get("ROUTER_DB_DIR", "/app/db")
DB_PATH = os.path.join(DB_DIR, "router.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_name TEXT NOT NULL,
            key_value TEXT NOT NULL UNIQUE,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


@router.get("/keys")
async def list_keys():
    """List all registered API keys (masked) from SQLite."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM api_keys ORDER BY created_at").fetchall()
    conn.close()
    return {
        "keys": [
            {
                "id": r["id"],
                "key_name": r["key_name"],
                "key_preview": f"***{r['key_value'][-4:]}" if len(r["key_value"]) > 6 else "***",
                "is_active": bool(r["is_active"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ],
        "default_key": settings.API_KEY,
    }


@router.post("/keys")
async def create_key(payload: dict):
    """Register a new API key with SQLite persistence."""
    key_value = payload.get("key_value", "").strip()
    key_name = payload.get("key_name", "unknown").strip()

    if not key_value or not key_value.startswith("sk-"):
        raise HTTPException(status_code=400, detail="Key must start with 'sk-'")
    if not key_name:
        raise HTTPException(status_code=400, detail="key_name is required")

    conn = _get_conn()
    existing = conn.execute("SELECT id FROM api_keys WHERE key_value = ?", (key_value,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=409, detail="Key already exists")

    conn.execute(
        "INSERT INTO api_keys (key_name, key_value, is_active) VALUES (?, ?, 1)",
        (key_name, key_value),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM api_keys ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()

    return {
        "status": "created",
        "id": row["id"],
        "key_name": row["key_name"],
        "key_preview": f"***{row['key_value'][-4:]}",
        "created_at": row["created_at"],
    }


@router.delete("/keys/{key_id}")
async def delete_key(key_id: int):
    """Delete an API key."""
    conn = _get_conn()
    row = conn.execute("SELECT id FROM api_keys WHERE id = ?", (key_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Key not found")
    conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": key_id}
