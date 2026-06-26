"""Three-tier tool registry.

Tier 1 — Platform builtins  (always available, defined in builtins.py)
Tier 2 — Project SQL tools  (dex.yaml  ai.tools  entries with a sql key)
Tier 3 — Project Python tools (tools/*.py files with @tool decorator)
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["ToolDef", "ToolRegistry", "get_registry", "tool"]


@dataclass
class ToolParam:
    name: str
    type: str = "str"
    required: bool = True
    default: Any = None
    description: str = ""


@dataclass
class ToolDef:
    name: str
    description: str
    tier: str  # "builtin" | "sql" | "python"
    params: list[ToolParam] = field(default_factory=list)
    sql_template: str = ""
    func: Callable[..., Any] | None = None
    source_file: str = ""


class ToolRegistry:
    """Unified catalog of all tools available to Intelligence agents."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool_def: ToolDef) -> None:
        self._tools[tool_def.name] = tool_def

    def register_builtin(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        params: list[ToolParam] | None = None,
    ) -> None:
        self.register(
            ToolDef(
                name=name,
                description=description,
                tier="builtin",
                params=params or [],
                func=func,
            )
        )

    def register_sql(
        self,
        name: str,
        description: str,
        sql: str,
        params: list[ToolParam] | None = None,
    ) -> None:
        self.register(
            ToolDef(
                name=name,
                description=description,
                tier="sql",
                sql_template=sql,
                params=params or [],
            )
        )

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def call(self, name: str, **kwargs: Any) -> Any:  # noqa: C901
        td = self.get(name)
        if td is None:
            raise KeyError(f"Tool '{name}' not found. Available: {self.names()}")

        if td.tier in ("builtin", "python") and td.func is not None:
            return td.func(**kwargs)

        if td.tier == "sql":
            return self._run_sql(td, kwargs)

        raise ValueError(f"Tool '{name}' has no callable implementation")

    def _run_sql(self, td: ToolDef, kwargs: dict[str, Any]) -> Any:
        """Execute a SQL template tool, validating and injecting typed params."""
        import re

        sql = td.sql_template
        for param in td.params:
            val = kwargs.get(param.name, param.default)
            if val is None and param.required:
                raise ValueError(f"Required param '{param.name}' missing for tool '{td.name}'")
            # safe numeric substitution; string params are quoted
            if param.type in ("int", "float"):
                sql = sql.replace(f"{{{param.name}}}", str(val))
            else:
                safe = str(val).replace("'", "''")
                sql = sql.replace(f"{{{param.name}}}", safe)
        # Fallback: replace any remaining {placeholders} with empty string
        # Cap length before regex to prevent ReDoS on unbounded user-supplied input
        if len(sql) > 65536:
            raise ValueError("SQL template exceeds maximum allowed length")
        sql = re.sub(r"\{[^}]+\}", "", sql)

        try:
            from dataenginex.ai.tools import (
                tool_registry as _dex_tr,  # type: ignore[import-untyped]
            )

            return _dex_tr.call("query", sql=sql)
        except Exception:
            import duckdb  # type: ignore[import-untyped]

            with duckdb.connect(":memory:") as conn:
                return conn.execute(sql).fetchdf()

    def load_from_config(self, eng: Any) -> None:
        """Load tier-2 SQL tools from dex.yaml ai.tools section."""
        with contextlib.suppress(Exception):
            ai_cfg = getattr(eng.config, "ai", None)
            tools_cfg = getattr(ai_cfg, "tools", None) or []
            if hasattr(tools_cfg, "items") and hasattr(tools_cfg, "values"):
                tools_cfg = list(tools_cfg.values())  # type: ignore[union-attr]
            for entry in tools_cfg:
                if isinstance(entry, dict):
                    name = str(entry.get("name", ""))
                    desc = str(entry.get("description", ""))
                    sql = str(entry.get("sql", ""))
                    raw_params = entry.get("params") or {}
                else:
                    name = str(getattr(entry, "name", ""))
                    desc = str(getattr(entry, "description", ""))
                    sql = str(getattr(entry, "sql", ""))
                    raw_params = getattr(entry, "params", None) or {}
                if not name or not sql:
                    continue

                def _pget(p: Any, k: str, d: Any = None) -> Any:
                    return p.get(k, d) if isinstance(p, dict) else getattr(p, k, d)

                params = [
                    ToolParam(
                        name=pname,
                        type=str(_pget(pconf, "type", "str")),
                        required=not bool(_pget(pconf, "default")),
                        default=_pget(pconf, "default"),
                    )
                    for pname, pconf in (raw_params.items() if hasattr(raw_params, "items") else [])
                ]
                self.register_sql(name, desc, sql, params)

    def load_from_project_dir(self, project_dir: Path) -> None:
        """Load tier-3 Python tools from tools/*.py files."""
        tools_dir = project_dir / "tools"
        if not tools_dir.is_dir():
            return
        for py_file in sorted(tools_dir.glob("*.py")):
            with contextlib.suppress(Exception):
                spec = importlib.util.spec_from_file_location(f"_dex_tools_{py_file.stem}", py_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)  # type: ignore[union-attr]
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if callable(attr) and getattr(attr, "_dex_tool", False):
                            self.register(
                                ToolDef(
                                    name=getattr(attr, "_dex_tool_name", attr_name),
                                    description=getattr(attr, "_dex_tool_desc", ""),
                                    tier="python",
                                    func=attr,
                                    source_file=str(py_file.name),
                                    params=_infer_params(attr),
                                )
                            )


def _infer_params(func: Callable[..., Any]) -> list[ToolParam]:
    """Derive ToolParam list from a function's type annotations and defaults."""
    params: list[ToolParam] = []
    with contextlib.suppress(Exception):
        sig = inspect.signature(func)
        hints = func.__annotations__ if hasattr(func, "__annotations__") else {}
        for pname, param in sig.parameters.items():
            if pname in ("self", "cls", "eng"):
                continue
            has_default = param.default is not inspect.Parameter.empty
            params.append(
                ToolParam(
                    name=pname,
                    type=str(
                        hints.get(pname, str).__name__
                        if hasattr(hints.get(pname, str), "__name__")
                        else "str"
                    ),
                    required=not has_default,
                    default=param.default if has_default else None,
                )
            )
    return params


# ── Decorator for project Python tools ───────────────────────────────────────


def tool(description: str = "") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that marks a function as a DEX Studio project tool."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func._dex_tool = True  # type: ignore[attr-defined]
        func._dex_tool_name = func.__name__  # type: ignore[attr-defined]
        func._dex_tool_desc = description or (func.__doc__ or "")  # type: ignore[attr-defined]
        return func

    return decorator


# ── Singleton registry ────────────────────────────────────────────────────────

_REGISTRY: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        from dex_studio.tools.builtins import register_builtins

        _REGISTRY = ToolRegistry()
        register_builtins(_REGISTRY)
    return _REGISTRY


def reset_registry() -> None:
    """Force reload — called when project changes."""
    global _REGISTRY
    _REGISTRY = None
