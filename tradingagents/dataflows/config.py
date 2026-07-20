"""Configuration loading with layered overrides.

Priority (highest → lowest):
  1. Environment variables (``TRADINGAGENTS_*``)
  2. ``config.yaml`` from project root (or ``TRADINGAGENTS_CONFIG`` env)
  3. ``tradingagents/default_config.py`` hardcoded defaults

Usage::

    from tradingagents.dataflows.config import get_config

    cfg = get_config()
    mode = cfg.get("analysis_mode", "full")
"""

import os
from typing import Dict, Optional

import tradingagents.default_config as default_config

_config: Optional[Dict] = None

# ── Helpers ──────────────────────────────────────────────────────────────────


def _find_config_yaml() -> Optional[str]:
    """Return path to config.yaml, or None.

    When ``TRADINGAGENTS_CONFIG`` is set in the environment it is used
    *authoritatively* — if it points at a non-existent file no fallback
    to the project-root ``config.yaml`` is attempted.
    """
    env_path = os.environ.get("TRADINGAGENTS_CONFIG")
    if env_path:
        return env_path if os.path.exists(env_path) else None
    default_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config.yaml"
    )
    return default_path if os.path.exists(default_path) else None


def _load_yaml_config() -> Optional[Dict]:
    """Load config.yaml into a dict. Returns None on any failure."""
    yaml_path = _find_config_yaml()
    if not yaml_path:
        return None
    try:
        import yaml

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "config.yaml 加载失败 (%s): %s", yaml_path, exc
        )
        return None


def _deep_merge(base: Dict, override: Dict) -> None:
    """Recursively merge ``override`` into ``base`` in-place.

    * Dict values at the same key are merged recursively.
    * ``None`` values in ``override`` are skipped (allow yaml ``null`` to
      mean "use default").
    """
    for key, value in override.items():
        if value is None:
            continue
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _apply_env_overrides(cfg: Dict) -> Dict:
    """Override config keys from ``TRADINGAGENTS_*`` environment variables.

    Boolean env values (``true``/``false``) are converted to Python bools;
    pure-digit strings to int; everything else kept as str.
    """
    env_map = {
        "TRADINGAGENTS_OUTPUT_LANGUAGE": "output_language",
        "TRADINGAGENTS_CHECKPOINT_ENABLED": "checkpoint_enabled",
        "TRADINGAGENTS_DEBATE_ROUNDS": "max_debate_rounds",
        "TRADINGAGENTS_RISK_DISCUSS_ROUNDS": "max_risk_discuss_rounds",
        "TRADINGAGENTS_MEMORY_LOG_MAX": "memory_log_max_entries",
        "TRADINGAGENTS_ANALYSIS_MODE": "analysis_mode",
        "TRADINGAGENTS_LLM_PROVIDER": "llm_provider",
        "TRADINGAGENTS_DEEP_THINK_LLM": "deep_think_llm",
        "TRADINGAGENTS_QUICK_THINK_LLM": "quick_think_llm",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key)
        if val is None:
            continue
        lower = val.strip().lower()
        if lower in ("true", "false"):
            cfg[cfg_key] = lower == "true"
        elif lower.isdigit():
            cfg[cfg_key] = int(lower)
        else:
            cfg[cfg_key] = val
    return cfg


# ── Public API ───────────────────────────────────────────────────────────────


def initialize_config() -> None:
    """Build the merged config from all layers.

    Called automatically on first import. Safe to call multiple times
    (idempotent if config is already loaded).
    """
    global _config
    if _config is not None:
        return

    cfg = default_config.DEFAULT_CONFIG.copy()

    yaml_cfg = _load_yaml_config()
    if yaml_cfg:
        _deep_merge(cfg, yaml_cfg)

    cfg = _apply_env_overrides(cfg)

    _config = cfg


def reset_config() -> None:
    """Force a full re-initialization on the next ``get_config()``.

    Useful in tests to reload config between cases with different
    environment variables or config.yaml content.
    """
    global _config
    _config = None


def set_config(cfg: Dict) -> None:
    """Apply runtime config overrides (e.g. from Web UI / CLI selections).

    These take the highest precedence — they are applied *after*
    defaults + yaml + env, and typically carry user choices from a
    menu (LLM provider, analysis mode, etc.).
    """
    global _config
    if _config is None:
        initialize_config()
    _config.update(cfg)


def get_config() -> Dict:
    """Return a **copy** of the current merged configuration."""
    if _config is None:
        initialize_config()
    return _config.copy()


# Initialize on first import.
initialize_config()
