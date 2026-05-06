"""Base Reflex state shared by all dex-studio state classes."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import reflex as rx

if TYPE_CHECKING:
    from dex_studio.engine import DexEngine


class BaseState(rx.State):
    """Common state fields and helpers inherited by all domain states.

    Provides loading/error flags, a toast queue, and safe access to the
    :class:`~dex_studio.engine.DexEngine` singleton.
    """

    is_loading: bool = False
    error: str = ""
    notification: str = ""
    toasts: list[dict[str, str]] = []

    def _push_toast(self, message: str, kind: str = "info") -> None:
        """Append a toast notification to the queue."""
        self.toasts = [*self.toasts, {"id": uuid.uuid4().hex[:8], "message": message, "kind": kind}]

    @rx.event
    def dismiss_toast(self, toast_id: str) -> None:
        """Remove a single toast by its ID."""
        self.toasts = [t for t in self.toasts if t["id"] != toast_id]

    @rx.event
    def clear_toasts(self) -> None:
        """Clear all pending toasts."""
        self.toasts = []

    def _engine(self) -> DexEngine:
        """Return the DexEngine singleton, raising RuntimeError if not yet initialised."""
        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            raise RuntimeError(
                "DexEngine not initialized — set DEX_CONFIG_PATH or call init_engine() at startup."
            )
        return eng

    def _engine_or_none(self) -> DexEngine | None:
        """Return the DexEngine singleton, or None if not yet initialised."""
        from dex_studio._engine import get_engine

        return get_engine()

    def _set_error(self, message: str) -> None:
        """Set the error field and push an error toast."""
        self.error = message
        self._push_toast(message, "error")
