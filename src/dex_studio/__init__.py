"""DEX Studio — local control plane for DataEngineX/DEX."""

from __future__ import annotations

try:
    from importlib.metadata import version

    __version__ = version("dex-studio")
except Exception:
    __version__ = "0.1.0"
