"""Integration test — verify app bootstraps and pages register."""

from __future__ import annotations


class TestAppBootstrap:
    def test_page_imports(self) -> None:
        """All page modules should import without error."""
        from dex_studio.pages import project_hub  # noqa: F401
        from dex_studio.pages.ai import (
            agents,  # noqa: F401
            collections,  # noqa: F401
            retrieval,  # noqa: F401
            tools,  # noqa: F401
        )
        from dex_studio.pages.ai import dashboard as ai_dash  # noqa: F401
        from dex_studio.pages.data import (
            dashboard,  # noqa: F401
            lineage,  # noqa: F401
            pipelines,  # noqa: F401
            quality,  # noqa: F401
            sources,  # noqa: F401
            warehouse,  # noqa: F401
        )
        from dex_studio.pages.ml import dashboard as ml_dash  # noqa: F401
        from dex_studio.pages.ml import (
            drift,  # noqa: F401
            experiments,  # noqa: F401
            features,  # noqa: F401
            models,  # noqa: F401
            predictions,  # noqa: F401
        )
        from dex_studio.pages.system import (
            components,  # noqa: F401
            connection,  # noqa: F401
            logs,  # noqa: F401
            metrics,  # noqa: F401
            settings,  # noqa: F401
            status,  # noqa: F401
            traces,  # noqa: F401
        )

    def test_components_import(self) -> None:
        """Layout components should import without error."""
        from dex_studio.components.layout import page_shell, sidebar  # noqa: F401

    def test_config_system(self) -> None:
        """Config loading should work with defaults."""
        from dex_studio.config import StudioConfig, load_config

        cfg = load_config()
        assert isinstance(cfg, StudioConfig)
        assert cfg.api_url == "http://localhost:17000"

    def test_client_creation(self) -> None:
        """DexClient should create from default config."""
        from dex_studio.client import DexClient
        from dex_studio.config import load_config

        cfg = load_config()
        client = DexClient(config=cfg)
        assert client.config.api_url == "http://localhost:17000"
