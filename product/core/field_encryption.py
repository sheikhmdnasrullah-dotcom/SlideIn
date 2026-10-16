"""Field-level encryption at rest for sensitive JSON columns.

Finding F4 (docs/decisions/ADR-2026-10-16-foundation-hardening-plan.md):
calendar credentials were stored as plaintext JSON. This module provides
Fernet (AES-128-CBC + HMAC) encryption with transparent handling — columns
using this decrypt on read and encrypt on write, and legacy plaintext rows
are tolerated: a value that does not decrypt is returned as-is so old rows
keep working until the next save re-encrypts them.

Key management
--------------
PRODUCT_FIELD_ENCRYPTION_KEY    Fernet key: URL-safe base64 encoding of 32
                                bytes. Generate one with:
                                python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Missing key behavior:
  * ENVIRONMENT=production  -> RuntimeError (fail fast at startup)
  * dev / test              -> fixed built-in development key, warned once
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_KEY_ENV = "PRODUCT_FIELD_ENCRYPTION_KEY"
_PRODUCTION = "production"

# Fixed, documented development/test key. Intentionally NOT a secret: it
# exists so dev and CI can run without configuration. Any environment that
# holds real credentials must set PRODUCT_FIELD_ENCRYPTION_KEY.
_DEV_KEY = base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef")

_lock = threading.Lock()
_cached: Optional[Fernet] = None
_warned_missing_key = False


def is_production() -> bool:
    return os.getenv("ENVIRONMENT", "development").strip().lower() == _PRODUCTION


def _resolve_key() -> bytes:
    global _warned_missing_key
    raw = os.getenv(_KEY_ENV, "").strip()
    if raw:
        try:
            Fernet(raw.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"{_KEY_ENV} is not a valid Fernet key (URL-safe base64, "
                f"32 bytes). Generate one with: "
                f'python -c "from cryptography.fernet import Fernet; '
                f'print(Fernet.generate_key().decode())"'
            ) from exc
        return raw.encode("utf-8")
    if is_production():
        raise RuntimeError(
            f"{_KEY_ENV} is required when ENVIRONMENT=production: "
            f"calendar credentials are encrypted at rest and cannot be "
            f"written without it. Generate a key with: "
            f'python -c "from cryptography.fernet import Fernet; '
            f'print(Fernet.generate_key().decode())"'
        )
    if not _warned_missing_key:
        _warned_missing_key = True
        logger.warning(
            "%s is not set; using the built-in development encryption key. "
            "Set %s before storing real credentials.",
            _KEY_ENV,
            _KEY_ENV,
        )
    return _DEV_KEY


def get_fernet() -> Fernet:
    """Process-wide Fernet, built from the configured (or dev) key."""
    global _cached
    if _cached is None:
        with _lock:
            if _cached is None:
                _cached = Fernet(_resolve_key())
    return _cached


def initialize() -> None:
    """Resolve the key now. Called at app startup so a missing production
    key fails fast instead of at the first credential write."""
    get_fernet()


def reset_cache() -> None:
    """Drop the cached Fernet and the missing-key warning flag (used by
    tests that change the environment)."""
    global _cached, _warned_missing_key
    with _lock:
        _cached = None
        _warned_missing_key = False


def encrypt_json(value: Any) -> Optional[str]:
    """Encrypt a JSON-serializable value to a Fernet token string."""
    if value is None:
        return None
    token = get_fernet().encrypt(json.dumps(value).encode("utf-8"))
    return token.decode("utf-8")


def decrypt_json(raw: Any) -> Any:
    """Decrypt a stored value back to its JSON form.

    Legacy plaintext rows (raw JSON, not a Fernet token) are returned
    unchanged; the next save of that row re-encrypts it.
    """
    if not isinstance(raw, str):
        return raw
    try:
        payload = get_fernet().decrypt(raw.encode("utf-8"))
    except (InvalidToken, TypeError, ValueError):
        return raw
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return raw
