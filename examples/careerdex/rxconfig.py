from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import reflex as rx

_port = int(os.getenv("PORT", "8788"))

config = rx.Config(
    app_name="careerdex",
    frontend_port=_port,
    backend_port=_port,
)
