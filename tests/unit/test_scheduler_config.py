from __future__ import annotations

import tempfile
from pathlib import Path

from dex_studio.scheduler import read_scheduler_config


def _make_eng(yaml_text: str) -> object:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_text)
        path = Path(f.name)

    class _Eng:
        config_path = path

    return _Eng()


def test_defaults_when_no_scheduler_block():
    eng = _make_eng("project:\n  name: test\n")
    cfg = read_scheduler_config(eng)
    assert cfg.enabled is True
    assert cfg.timezone == "UTC"
    assert cfg.max_concurrent == 3
    assert cfg.retry_attempts == 2
    assert cfg.retry_backoff_s == 60
    assert cfg.on_complete == {}


def test_enabled_true():
    eng = _make_eng("scheduler:\n  enabled: true\n")
    cfg = read_scheduler_config(eng)
    assert cfg.enabled is True


def test_custom_retry():
    eng = _make_eng(
        "scheduler:\n  enabled: true\n  retry:\n    max_attempts: 5\n    backoff_seconds: 120\n"
    )
    cfg = read_scheduler_config(eng)
    assert cfg.retry_attempts == 5
    assert cfg.retry_backoff_s == 120


def test_on_complete_parsed():
    yaml_text = (
        "scheduler:\n"
        "  enabled: true\n"
        "  on_pipeline_complete:\n"
        "    gold_features:\n"
        "      trigger_ml_retrain: true\n"
        "      ml_experiment: predictor\n"
    )
    eng = _make_eng(yaml_text)
    cfg = read_scheduler_config(eng)
    assert cfg.on_complete["gold_features"]["trigger_ml_retrain"] is True


def test_no_config_path_returns_defaults():
    class _NoPath:
        config_path = None

    cfg = read_scheduler_config(_NoPath())
    assert cfg.enabled is True


def test_missing_file_returns_defaults():
    class _BadPath:
        config_path = Path("/nonexistent/dex.yaml")

    cfg = read_scheduler_config(_BadPath())
    assert cfg.enabled is True
