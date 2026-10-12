"""Shared API-key check for local review/dev HTTP servers.

dashboard_server.py and sent_emails_review_server.py are browser-viewed
local tools, so they accept the workspace key via header (API style) or
``?api_key=`` query param (browser style) and validate it against the
same workspaces table as the main API server. Rejects fail closed.
"""
from __future__ import annotations

import hmac
import sqlite3
from pathlib import Path
from typing import Dict, List, Mapping


def extract_key(headers: Mapping[str, str], query=None) -> str:
    """Pull the caller's API key from header first, then query param."""
    key = headers.get("X-API-Key") or ""
    if not key:
        auth = headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            key = auth[len("Bearer "):]
        elif auth:
            key = auth
    if not key and query:
        values = query.get("api_key", [])
        if values:
            key = values[0]
    return key


def is_valid_workspace_key(db_path: str | Path, key: str) -> bool:
    """True iff key matches a workspace key in constant time.

    Any failure (missing DB, missing table, empty key) means invalid.
    """
    if not key:
        return False
    try:
        conn = sqlite3.connect(str(db_path))
    except Exception:
        return False
    try:
        try:
            rows = conn.execute("SELECT api_key FROM workspaces").fetchall()
        except Exception:
            return False
    finally:
        conn.close()
    return any(
        row[0] and hmac.compare_digest(str(row[0]), key) for row in rows
    )
