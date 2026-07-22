"""Deterministic, code-owned data collection for every analyst run.

The LLM never decides which tools to call.  This module builds a fixed request
plan from the selected analysis scope, executes it once, and stores a timestamped
snapshot plus the existing sanitized quality/performance ledgers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
import time
from typing import Any, Callable, Iterable, Mapping

from tradingagents.agents.quality_ledger import (
    ANALYST_EXPECTED_TOOLS,
    STATUS_FAILED,
    STATUS_INVALID_INPUT,
    build_direct_tool_ledger_entry,
    expected_tools_for_analysts,
)
from tradingagents.agents.utils.agent_utils import (
    get_balance_sheet,
    get_cashflow,
    get_concept_blocks,
    get_dragon_tiger_board,
    get_fund_flow,
    get_fundamentals,
    get_global_news,
    get_hot_stocks,
    get_income_statement,
    get_indicators,
    get_industry_comparison,
    get_insider_transactions,
    get_lockup_expiry,
    get_news,
    get_northbound_flow,
    get_profit_forecast,
    get_stock_data,
)


logger = logging.getLogger(__name__)

SNAPSHOT_SCHEMA_VERSION = 1
DEFAULT_INDICATORS = (
    "close_10_ema",
    "close_50_sma",
    "macd",
    "macds",
    "macdh",
    "rsi",
    "boll",
    "atr",
)

_INDICATOR_LABELS = {
    "close_10_ema": "10日指数均线",
    "close_50_sma": "50日均线",
    "macd": "趋势动量线",
    "macds": "趋势信号线",
    "macdh": "趋势动量柱",
    "rsi": "相对强弱指标",
    "boll": "价格波动中轨",
    "atr": "平均波动幅度",
}

_STATUS_LABELS = {
    "success": "成功",
    "normal_empty": "正常无记录",
    "failed": "获取失败",
    "invalid_input": "输入无效",
}

DEFAULT_TOOL_REGISTRY: Mapping[str, Any] = {
    "get_stock_data": get_stock_data,
    "get_indicators": get_indicators,
    "get_news": get_news,
    "get_global_news": get_global_news,
    "get_insider_transactions": get_insider_transactions,
    "get_fundamentals": get_fundamentals,
    "get_balance_sheet": get_balance_sheet,
    "get_cashflow": get_cashflow,
    "get_income_statement": get_income_statement,
    "get_profit_forecast": get_profit_forecast,
    "get_industry_comparison": get_industry_comparison,
    "get_hot_stocks": get_hot_stocks,
    "get_northbound_flow": get_northbound_flow,
    "get_concept_blocks": get_concept_blocks,
    "get_fund_flow": get_fund_flow,
    "get_dragon_tiger_board": get_dragon_tiger_board,
    "get_lockup_expiry": get_lockup_expiry,
}


@dataclass(frozen=True)
class SnapshotRequest:
    request_id: str
    tool_name: str
    label: str
    args: dict[str, Any]
    audiences: tuple[str, ...]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_window(trade_date: str, days: int) -> str:
    try:
        parsed = date.fromisoformat(trade_date)
    except ValueError:
        return trade_date
    return (parsed - timedelta(days=days)).isoformat()


def _audiences(tool_name: str, selected_analysts: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        analyst
        for analyst in selected_analysts
        if tool_name in ANALYST_EXPECTED_TOOLS.get(analyst, set())
    )


def build_snapshot_requests(
    ticker: str,
    trade_date: str,
    selected_analysts: Iterable[str],
) -> list[SnapshotRequest]:
    """Build the canonical request plan for a full or reduced analysis scope."""
    selected = tuple(selected_analysts)
    expected = expected_tools_for_analysts(selected)
    news_start = _date_window(trade_date, 30)
    price_start = _date_window(trade_date, 120)

    definitions: list[tuple[str, str, dict[str, Any]]] = [
        (
            "get_stock_data",
            "股价和成交量",
            {"symbol": ticker, "start_date": price_start, "end_date": trade_date},
        ),
        (
            "get_news",
            "相关新闻",
            {"ticker": ticker, "start_date": news_start, "end_date": trade_date},
        ),
        (
            "get_global_news",
            "市场新闻",
            {"curr_date": trade_date, "look_back_days": 14, "limit": 10},
        ),
        ("get_insider_transactions", "股东交易", {"ticker": ticker}),
        (
            "get_fundamentals",
            "公司基本情况",
            {"ticker": ticker, "curr_date": trade_date},
        ),
        (
            "get_balance_sheet",
            "资产负债情况",
            {"ticker": ticker, "freq": "quarterly", "curr_date": trade_date},
        ),
        (
            "get_cashflow",
            "现金流情况",
            {"ticker": ticker, "freq": "quarterly", "curr_date": trade_date},
        ),
        (
            "get_income_statement",
            "利润情况",
            {"ticker": ticker, "freq": "quarterly", "curr_date": trade_date},
        ),
        ("get_profit_forecast", "机构预期", {"ticker": ticker}),
        (
            "get_industry_comparison",
            "所属行业情况",
            {"ticker": ticker, "curr_date": trade_date},
        ),
        ("get_hot_stocks", "市场热门股", {"curr_date": trade_date}),
        (
            "get_northbound_flow",
            "外资流向",
            {"curr_date": trade_date, "include_history": True},
        ),
        ("get_concept_blocks", "概念板块", {"ticker": ticker}),
        (
            "get_fund_flow",
            "资金流向",
            {"ticker": ticker, "curr_date": trade_date, "include_history": True},
        ),
        (
            "get_dragon_tiger_board",
            "龙虎榜",
            {"ticker": ticker, "curr_date": trade_date, "look_back_days": 30},
        ),
        (
            "get_lockup_expiry",
            "限售股解禁",
            {"ticker": ticker, "curr_date": trade_date, "forward_days": 90},
        ),
    ]

    indicator_requests: list[SnapshotRequest] = []
    if "get_indicators" in expected:
        for indicator in DEFAULT_INDICATORS:
            indicator_requests.append(SnapshotRequest(
                request_id=f"get_indicators:{indicator}",
                tool_name="get_indicators",
                label=f"技术指标：{_INDICATOR_LABELS[indicator]}",
                args={
                    "symbol": ticker,
                    "indicator": indicator,
                    "curr_date": trade_date,
                    "look_back_days": 30,
                },
                audiences=_audiences("get_indicators", selected),
            ))

    requests: list[SnapshotRequest] = []
    for tool_name, label, args in definitions:
        if tool_name not in expected:
            continue
        requests.append(SnapshotRequest(
            request_id=tool_name,
            tool_name=tool_name,
            label=label,
            args=args,
            audiences=_audiences(tool_name, selected),
        ))
        if tool_name == "get_stock_data":
            requests.extend(indicator_requests)

    planned_tools = {request.tool_name for request in requests}
    unplanned_tools = expected - planned_tools
    if unplanned_tools:
        missing = ", ".join(sorted(unplanned_tools))
        raise RuntimeError(f"snapshot plan is missing required tools: {missing}")
    return requests


def _invoke_tool(
    tool: Any,
    args: dict[str, Any],
    runtime_config: dict[str, Any] | None = None,
) -> Any:
    if hasattr(tool, "invoke"):
        return tool.invoke(args, config=runtime_config)
    if callable(tool):
        return tool(**args)
    raise TypeError("snapshot tool is not callable")


def collect_data_snapshot(
    ticker: str,
    trade_date: str,
    selected_analysts: Iterable[str],
    *,
    tool_registry: Mapping[str, Any] | None = None,
    clock: Callable[[], str] = _iso_now,
    runtime_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the fixed plan once and return snapshot plus sanitized ledgers."""
    selected = tuple(selected_analysts)
    registry = tool_registry or DEFAULT_TOOL_REGISTRY
    requests = build_snapshot_requests(ticker, trade_date, selected)
    snapshot_started_at = clock()
    records: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    performance: list[dict[str, Any]] = []

    for request in requests:
        started_at = clock()
        started = time.perf_counter()
        try:
            content = _invoke_tool(
                registry[request.tool_name],
                request.args,
                runtime_config,
            )
        except Exception as exc:  # noqa: BLE001 - convert to sanitized data status
            logger.warning(
                "确定性数据快照采集失败：%s（%s）",
                request.tool_name,
                type(exc).__name__,
            )
            content = "工具调用失败"
        finished_at = clock()
        duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        entry = build_direct_tool_ledger_entry(
            request.tool_name,
            request.args,
            content,
            request_label=request.label,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
        )
        ledger.append(entry)
        performance.append({
            "kind": "tool",
            "name": request.tool_name,
            "stage": "data_snapshot",
            "analyst": "snapshot",
            "status": entry["status"],
            "cache_hit": False,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
        })
        usable = entry["status"] not in {STATUS_FAILED, STATUS_INVALID_INPUT}
        records.append({
            "request_id": request.request_id,
            "tool_name": request.tool_name,
            "label": request.label,
            "audiences": list(request.audiences),
            "status": entry["status"],
            "collected_at": finished_at,
            "duration_ms": duration_ms,
            "content": str(content) if usable else "",
        })

    status_counts = dict(Counter(record["status"] for record in records))
    fingerprint_payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "ticker": ticker,
        "trade_date": trade_date,
        "selected_analysts": list(selected),
        "records": [
            {
                "request_id": record["request_id"],
                "status": record["status"],
                "content": record["content"],
            }
            for record in records
        ],
    }
    snapshot_id = hashlib.sha256(json.dumps(
        fingerprint_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()[:16]
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "collection_policy": "deterministic-v1",
        "ticker": ticker,
        "trade_date": trade_date,
        "selected_analysts": list(selected),
        "started_at": snapshot_started_at,
        "completed_at": clock(),
        "request_count": len(records),
        "status_counts": status_counts,
        "records": records,
    }
    return {
        "data_snapshot": snapshot,
        "tool_execution_ledger": ledger,
        "performance_ledger": performance,
    }


def create_data_snapshot_node(
    tool_registry: Mapping[str, Any] | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Create the graph node that always runs before analyst fan-out."""
    def data_snapshot_node(
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return collect_data_snapshot(
            str(state["company_of_interest"]),
            str(state["trade_date"]),
            state.get("selected_analysts", []),
            tool_registry=tool_registry,
            runtime_config=config,
        )

    return data_snapshot_node


def render_snapshot_for_analyst(
    snapshot: dict[str, Any],
    analyst: str,
) -> str:
    """Render only the read-only snapshot sections assigned to one analyst."""
    records = [
        record
        for record in snapshot.get("records", [])
        if analyst in record.get("audiences", [])
    ]
    lines = [
        "## 代码预先采集的数据快照",
        f"- 股票：{snapshot.get('ticker', '')}",
        f"- 分析日期：{snapshot.get('trade_date', '')}",
        f"- 快照编号：{snapshot.get('snapshot_id', '')}",
        f"- 快照完成时间：{snapshot.get('completed_at', '')}",
        "- 规则：只能使用下列数据；失败或未提供的栏目必须明确写无法判断，禁止猜测。",
    ]
    if not records:
        lines.append("\n[数据缺失：本分析角度没有可用快照栏目]")
        return "\n".join(lines)

    for record in records:
        status = record.get("status")
        lines.extend([
            "",
            f"### {record.get('label')}",
            f"状态：{_STATUS_LABELS.get(str(status), '未知')}",
        ])
        content = str(record.get("content", "")).strip()
        if content:
            lines.append(content)
        else:
            lines.append(f"[数据缺失：{record.get('label')}未获取]")
    return "\n".join(lines)
