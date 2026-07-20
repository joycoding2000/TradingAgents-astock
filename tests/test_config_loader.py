"""Tests for the layered config loader (config.yaml + env + defaults)."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml


# ── Helper: simulate a config.yaml on disk ────────────────────────────────


@pytest.fixture
def mock_yaml():
    """Write a temporary config.yaml and set TRADINGAGENTS_CONFIG to point at it.

    Yields the path; cleanup happens on teardown.
    """
    cfg = {
        "output_language": "English",
        "max_debate_rounds": 3,
        "checkpoint_enabled": True,
        "memory_log_max_entries": 50,
        "data_vendors": {
            "core_stock_apis": "tushare",
        },
        "llm_provider": "deepseek",
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    yaml.dump(cfg, tmp)
    tmp.close()

    old_env = os.environ.get("TRADINGAGENTS_CONFIG")
    os.environ["TRADINGAGENTS_CONFIG"] = tmp.name
    yield Path(tmp.name)
    os.unlink(tmp.name)
    if old_env is None:
        del os.environ["TRADINGAGENTS_CONFIG"]
    else:
        os.environ["TRADINGAGENTS_CONFIG"] = old_env


# ── Fixture: clean config between tests ───────────────────────────────────


@pytest.fixture(autouse=True)
def fresh_config():
    """Reset the config singleton before each test."""
    from tradingagents.dataflows.config import reset_config

    reset_config()
    yield
    reset_config()


# ── Tests ──────────────────────────────────────────────────────────────────


def test_get_config_returns_defaults_when_no_yaml():
    """Without any config.yaml, get_config() returns default_config values."""
    old = os.environ.get("TRADINGAGENTS_CONFIG")
    os.environ["TRADINGAGENTS_CONFIG"] = "/nonexistent/force-no-yaml.yaml"

    from tradingagents.dataflows.config import get_config

    cfg = get_config()
    assert cfg["max_debate_rounds"] == 1
    assert cfg["checkpoint_enabled"] is False
    assert cfg["output_language"] == "Chinese"

    if old is None:
        del os.environ["TRADINGAGENTS_CONFIG"]
    else:
        os.environ["TRADINGAGENTS_CONFIG"] = old


def test_yaml_overrides_defaults(mock_yaml):
    """config.yaml values take precedence over hardcoded defaults."""
    from tradingagents.dataflows.config import get_config

    cfg = get_config()
    assert cfg["max_debate_rounds"] == 3
    assert cfg["checkpoint_enabled"] is True
    assert cfg["output_language"] == "English"
    assert cfg["llm_provider"] == "deepseek"


def test_yaml_merges_nested_dicts(mock_yaml):
    """Partial data_vendors in yaml merges with defaults, does not replace."""
    from tradingagents.dataflows.config import get_config

    cfg = get_config()
    assert cfg["data_vendors"]["core_stock_apis"] == "tushare"
    assert cfg["data_vendors"]["technical_indicators"] == "a_stock"
    assert cfg["data_vendors"]["fundamental_data"] == "a_stock"


def test_yaml_keeps_unspecified_keys(mock_yaml):
    """Keys not in config.yaml keep their default values."""
    from tradingagents.dataflows.config import get_config

    cfg = get_config()
    assert cfg["max_risk_discuss_rounds"] == 1  # not in mock_yaml → default


def test_env_var_overrides_yaml(mock_yaml):
    """TRADINGAGENTS_* env var beats config.yaml."""
    os.environ["TRADINGAGENTS_DEBATE_ROUNDS"] = "5"

    from tradingagents.dataflows.config import get_config

    cfg = get_config()
    assert cfg["max_debate_rounds"] == 5

    del os.environ["TRADINGAGENTS_DEBATE_ROUNDS"]


def test_env_bool_parsing():
    """TRADINGAGENTS_CHECKPOINT_ENABLED=false should produce False."""
    os.environ["TRADINGAGENTS_CHECKPOINT_ENABLED"] = "false"

    from tradingagents.dataflows.config import get_config

    cfg = get_config()
    assert cfg["checkpoint_enabled"] is False

    del os.environ["TRADINGAGENTS_CHECKPOINT_ENABLED"]


def test_get_config_returns_copy():
    """get_config() returns a new dict each time, preventing mutation leaks."""
    from tradingagents.dataflows.config import get_config

    c1 = get_config()
    c2 = get_config()
    assert c1 is not c2
    c1["max_debate_rounds"] = 999
    assert c2["max_debate_rounds"] != 999


def test_set_config_runtime_override():
    """set_config() applied after all layers, highest precedence."""
    from tradingagents.dataflows.config import get_config, set_config

    set_config({"max_debate_rounds": 7})
    cfg = get_config()
    assert cfg["max_debate_rounds"] == 7


def test_yaml_not_found_fallback():
    """Non-existent config.yaml path silently falls back to defaults."""
    os.environ["TRADINGAGENTS_CONFIG"] = "/nonexistent/path/config.yaml"

    from tradingagents.dataflows.config import get_config

    cfg = get_config()
    assert cfg["max_debate_rounds"] == 1

    del os.environ["TRADINGAGENTS_CONFIG"]
