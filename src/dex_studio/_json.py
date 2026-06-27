"""orjson-backed JSON helpers — drop-in replacement for stdlib json."""

from __future__ import annotations

from typing import Any

import orjson


def dumps(obj: Any, *, indent: int | None = None, default: Any = None) -> str:
    """Serialize *obj* to a JSON string, with optional pretty-print and default serializer."""
    option = orjson.OPT_INDENT_2 if indent else None
    raw: bytes = orjson.dumps(obj, option=option, default=default)
    return raw.decode()


def dumpb(obj: Any, *, indent: int | None = None, default: Any = None) -> bytes:
    """Serialize *obj* to a JSON byte-string, with optional pretty-print and default serializer."""
    option = orjson.OPT_INDENT_2 if indent else None
    raw: bytes = orjson.dumps(obj, option=option, default=default)
    return raw


def loads(s: str | bytes) -> Any:
    """Deserialize a JSON string or byte-string to a Python object."""
    return orjson.loads(s)
