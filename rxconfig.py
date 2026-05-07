from __future__ import annotations

import sys
from pathlib import Path

# src-layout: add src/ so Reflex can find the dex_studio package
sys.path.insert(0, str(Path(__file__).parent / "src"))

import reflex as rx
from reflex_base.plugins.sitemap import SitemapPlugin

config = rx.Config(
    app_name="dex_studio",
    frontend_port=7860,
    backend_port=8787,
    env=rx.Env.DEV,
    disable_plugins=[SitemapPlugin],
)
