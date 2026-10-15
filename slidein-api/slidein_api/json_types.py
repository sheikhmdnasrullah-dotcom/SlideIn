"""Portable JSON column types.

The canonical model must run on SQLite (local workspace + tests) and
PostgreSQL (deployment) without a second model definition, so these
TypeDecorators serialize to a TEXT column everywhere.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


class JSONType(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, default_factory=None, **kwargs):
        super().__init__(**kwargs)
        self._default_factory = default_factory

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8", "replace")
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None

    def copy(self, **kwargs) -> "JSONType":
        # SQLAlchemy requires copy() to preserve the concrete subclass.
        return type(self)(default_factory=self._default_factory)

    def _maybe_default(self):
        if self._default_factory is None:
            return None
        return self._default_factory()


class JSONMap(JSONType):
    def process_result_value(self, value, dialect):  # type: ignore[override]
        parsed = super().process_result_value(value, dialect)
        return parsed if isinstance(parsed, dict) else (self._maybe_default() or {})


class JSONList(JSONType):
    def process_result_value(self, value, dialect):  # type: ignore[override]
        parsed = super().process_result_value(value, dialect)
        return parsed if isinstance(parsed, list) else (self._maybe_default() or [])
