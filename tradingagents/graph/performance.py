"""Run-local performance instrumentation without prompts or response bodies."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import inspect
import math
import threading
import time
from typing import Any, Callable, Iterable

from langchain_core.callbacks import BaseCallbackHandler


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def make_timing_entry(
    *,
    kind: str,
    name: str,
    status: str,
    started_at: str,
    duration_ms: int,
    stage: str = "",
    **extra: Any,
) -> dict[str, Any]:
    """Build a timing record containing no prompts, results, args or errors."""
    entry: dict[str, Any] = {
        "kind": kind,
        "name": name,
        "status": status,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "duration_ms": max(0, int(duration_ms)),
    }
    if stage:
        entry["stage"] = stage
    entry.update(extra)
    return entry


def timed_node(
    name: str,
    node: Callable[..., dict[str, Any]],
    *,
    stage: str,
    kind: str = "node",
) -> Callable[..., dict[str, Any]]:
    """Wrap a graph node and append one additive performance-ledger record."""
    parameters = inspect.signature(node).parameters
    accepts_config = "config" in parameters or len(parameters) >= 2

    @wraps(node)
    def invoke(state: dict[str, Any], config: Any = None) -> dict[str, Any]:
        started_at = _utc_now()
        started = time.perf_counter()
        try:
            outcome = node(state, config) if accepts_config else node(state)
        except Exception:
            # Failed graph nodes cannot safely return a state update. The exception
            # remains visible in normal logs and checkpoints; no sensitive text is
            # copied into a result that did not complete.
            raise
        entry = make_timing_entry(
            kind=kind,
            name=name,
            status="success",
            started_at=started_at,
            duration_ms=_duration_ms(started),
            stage=stage,
        )
        result = dict(outcome or {})
        existing = list(result.get("performance_ledger", []))
        result["performance_ledger"] = existing + [entry]
        return result

    return invoke


class ModelTimingCallback(BaseCallbackHandler):
    """Thread-safe callback recording one sanitized entry per model round."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._active: dict[str, tuple[float, str, str]] = {}
        self._entries: list[dict[str, Any]] = []

    @staticmethod
    def _model_name(serialized: dict[str, Any], kwargs: dict[str, Any]) -> str:
        params = kwargs.get("invocation_params") or {}
        model = params.get("model") or params.get("model_name")
        if model:
            return str(model)
        return str(serialized.get("name") or serialized.get("id", ["模型"])[-1])

    def _start(self, serialized: dict[str, Any], kwargs: dict[str, Any]) -> None:
        run_id = str(kwargs.get("run_id", ""))
        if not run_id:
            return
        with self._lock:
            self._active[run_id] = (
                time.perf_counter(),
                _utc_now(),
                self._model_name(serialized, kwargs),
            )

    def on_llm_start(self, serialized, prompts, **kwargs: Any) -> None:
        self._start(serialized, kwargs)

    def on_chat_model_start(self, serialized, messages, **kwargs: Any) -> None:
        self._start(serialized, kwargs)

    def _finish(self, status: str, kwargs: dict[str, Any]) -> None:
        run_id = str(kwargs.get("run_id", ""))
        with self._lock:
            active = self._active.pop(run_id, None)
        if active is None:
            return
        started, started_at, model = active
        entry = make_timing_entry(
            kind="model",
            name=model,
            status=status,
            started_at=started_at,
            duration_ms=_duration_ms(started),
            stage="model",
        )
        with self._lock:
            self._entries.append(entry)

    def on_llm_end(self, response, **kwargs: Any) -> None:
        self._finish("success", kwargs)

    def on_llm_error(self, error, **kwargs: Any) -> None:
        self._finish("failed", kwargs)

    def reset(self) -> None:
        with self._lock:
            self._active.clear()
            self._entries.clear()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(entry) for entry in self._entries]


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def summarize_performance_ledger(
    ledger: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize timings for Web display and before/after comparisons."""
    entries = list(ledger or [])
    model_durations = [
        int(entry.get("duration_ms", 0))
        for entry in entries
        if entry.get("kind") == "model"
    ]
    tool_entries = [entry for entry in entries if entry.get("kind") == "tool"]
    tool_durations = [int(entry.get("duration_ms", 0)) for entry in tool_entries]
    wall_entries = [
        entry for entry in entries if entry.get("kind") in {"run", "persistence"}
    ]
    cache_hits = sum(1 for entry in tool_entries if entry.get("cache_hit"))

    stage_totals: dict[str, int] = {}
    for entry in entries:
        if entry.get("kind") != "stage":
            continue
        stage = str(entry.get("stage") or "other")
        stage_totals[stage] = stage_totals.get(stage, 0) + int(
            entry.get("duration_ms", 0)
        )

    return {
        "wall_duration_ms": sum(int(entry.get("duration_ms", 0)) for entry in wall_entries),
        "model_call_count": len(model_durations),
        "model_total_duration_ms": sum(model_durations),
        "model_p50_duration_ms": _percentile(model_durations, 0.50),
        "model_p95_duration_ms": _percentile(model_durations, 0.95),
        "tool_call_count": len(tool_durations),
        "tool_total_duration_ms": sum(tool_durations),
        "tool_p50_duration_ms": _percentile(tool_durations, 0.50),
        "tool_p95_duration_ms": _percentile(tool_durations, 0.95),
        "cache_hit_count": cache_hits,
        "cache_hit_rate": round(cache_hits / len(tool_entries), 4) if tool_entries else 0.0,
        "stage_duration_ms": stage_totals,
    }
