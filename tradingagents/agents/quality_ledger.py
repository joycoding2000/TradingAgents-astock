"""代码层数据工具台账：记录每次工具调用的最终数据状态。

台账只保存工具名、分析师和状态，不保存工具返回正文或网络错误，避免把底层实现细节
带入产品结果。质量门控据此判断数据可信度，LLM 仅负责解释缺失的投资含义。
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable


STATUS_SUCCESS = "success"
STATUS_NORMAL_EMPTY = "normal_empty"
STATUS_FAILED = "failed"
STATUS_INVALID_INPUT = "invalid_input"

_STATUS_LABELS = {
    STATUS_SUCCESS: "成功",
    STATUS_NORMAL_EMPTY: "正常空结果",
    STATUS_FAILED: "失败",
    STATUS_INVALID_INPUT: "输入无效",
}

# 台账在网页中展示，工具的内部英文名不能直接暴露给普通用户。
_TOOL_LABELS = {
    "get_stock_data": "股价和成交量",
    "get_indicators": "技术指标",
    "get_fundamentals": "公司基本情况",
    "get_balance_sheet": "资产负债情况",
    "get_cashflow": "现金流情况",
    "get_income_statement": "利润情况",
    "get_news": "相关新闻",
    "get_fund_flow": "资金流向",
    "get_industry_comparison": "所属行业情况",
    "get_northbound_flow": "外资流向",
    "get_profit_forecast": "机构预期",
    "get_hot_stocks": "市场热门股",
    "get_concept_blocks": "概念板块",
    "get_dragon_tiger_board": "龙虎榜",
    "get_lockup_expiry": "限售股解禁",
    "get_insider_transactions": "股东交易",
    "get_global_news": "市场新闻",
}

# 只有行情价格是所有结论共同依赖的硬基础。其他接口失败时，应限制对应领域的结论，
# 而不是一票否决整份综合报告。
BLOCKING_TOOLS = {"get_stock_data"}

# 两个主要研究领域同时完全不可用时，综合报告才降为低可信度。单个领域不可用、或某个
# 补充接口失败，均降为中可信度并禁止使用相应论据。
CORE_DOMAINS = {
    "行情与技术": {"get_stock_data", "get_indicators"},
    "公司经营": {
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
    },
    "新闻与政策": {"get_news", "get_global_news"},
}

TOOL_CLAIM_CONSTRAINTS = {
    "get_stock_data": "不能判断股价趋势、涨跌幅、成交量，也不能给出参考价位",
    "get_indicators": "不能使用技术指标判断趋势、超买超卖或支撑压力",
    "get_fundamentals": "不能判断公司综合估值和核心经营情况",
    "get_balance_sheet": "不能判断资产负债结构和偿债能力",
    "get_cashflow": "不能判断公司现金进出和盈利质量",
    "get_income_statement": "不能判断收入、利润及其变化趋势",
    "get_news": "不能断言公司近期存在或不存在特定消息、公告和舆情事件",
    "get_global_news": "不能判断近期宏观和市场消息影响",
    "get_fund_flow": "不能判断主力资金流入、流出、抢筹或出逃",
    "get_industry_comparison": "不能判断行业排名、行业强弱和板块轮动",
    "get_northbound_flow": "不能判断外资流入或流出",
    "get_profit_forecast": "不能判断机构盈利预期和预测估值",
    "get_hot_stocks": "不能判断是否属于当日热门股或热门题材",
    "get_concept_blocks": "不能确认所属概念和板块",
    "get_dragon_tiger_board": "不能判断龙虎榜席位和机构参与情况",
    "get_lockup_expiry": "不能判断限售股解禁时间和规模",
    "get_insider_transactions": "不能判断股东和公司管理人员的持股变化",
}

_NORMAL_EMPTY_MARKERS = (
    "未上龙虎榜",
    "无历史解禁记录",
    "无待解禁",
    "No realtime fund flow",
    "北向资金当日无数据",
)

_FAILURE_MARKERS = (
    "[数据缺失",
    "Error fetching",
    "Error retrieving",
    "数据获取失败",
    "数据暂不可用",
    "获取失败",
    "查询失败",
    "无法获取",
    "No data found",
    "工具调用失败",
    "数据获取为空",
    "No global news found",
    "No shareholder data found",
    "No concept/block data",
)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value or "")


def _request_key(call: dict[str, Any]) -> str:
    """同一工具、同一参数的重试共用键；只存不可逆摘要，不存参数正文。"""
    raw = json.dumps(
        {"tool_name": str(call.get("name", "unknown_tool")), "args": call.get("args", {})},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _tool_label(tool_name: str) -> str:
    return _TOOL_LABELS.get(tool_name, "数据工具")


def classify_tool_result(content: Any, message_status: str | None = None) -> str:
    """将工具结果归为成功、正常空结果、失败或输入无效。"""
    text = _text(content).strip()
    if message_status == "error" or not text:
        return STATUS_FAILED
    if "Invalid ticker" in text or "只接受 6 位代码" in text:
        return STATUS_INVALID_INPUT
    if any(marker in text for marker in _FAILURE_MARKERS):
        return STATUS_FAILED
    if any(marker in text for marker in _NORMAL_EMPTY_MARKERS):
        return STATUS_NORMAL_EMPTY
    return STATUS_SUCCESS


def build_tool_ledger(
    analyst: str, tool_calls: Iterable[dict[str, Any]], tool_messages: Iterable[Any]
) -> list[dict[str, Any]]:
    """将一次 ToolNode 执行转换为无敏感正文的台账记录。"""
    by_call_id = {
        str(getattr(message, "tool_call_id", "")): message
        for message in tool_messages
    }
    recorded_at = datetime.now(timezone.utc).isoformat()
    ledger = []
    for call in tool_calls:
        tool_name = str(call.get("name", "unknown_tool"))
        call_id = str(call.get("id", ""))
        message = by_call_id.get(call_id)
        status = classify_tool_result(
            getattr(message, "content", ""), getattr(message, "status", None)
        )
        ledger.append(
            {
                "tool_name": tool_name,
                "analyst": analyst,
                "status": status,
                "critical": tool_name in BLOCKING_TOOLS,
                "impact": "基础" if tool_name in BLOCKING_TOOLS else "分项",
                "tool_call_id": call_id,
                "request_key": _request_key(call),
                "recorded_at": recorded_at,
            }
        )
    return ledger


def create_tracked_tool_node(analyst: str, tools: list[Any]):
    """创建 ToolNode 包装器，在不改变 ToolMessage 的前提下附加台账。"""
    from langgraph.prebuilt import ToolNode

    node = ToolNode(tools)

    def invoke(state, config=None):
        # ToolNode 需要沿用 LangGraph 传入的 runtime/config；否则工具节点在图外
        # 单独调用时会缺少运行时上下文。
        outcome = node.invoke(state, config)
        calls = getattr(state["messages"][-1], "tool_calls", [])
        ledger = build_tool_ledger(analyst, calls, outcome.get("messages", []))
        return {**outcome, "tool_execution_ledger": ledger}

    return invoke


def summarize_tool_ledger(ledger: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """按相同请求的最后一次调用汇总，成功重试可覆盖之前的临时失败。"""
    entries = list(ledger or [])
    latest_by_request: dict[str, dict[str, Any]] = {}
    for entry in entries:
        # 兼容 v0.2.23 已持久化的旧台账；旧记录没有请求摘要时按工具名汇总。
        request_key = str(entry.get("request_key") or entry.get("tool_name", "unknown_tool"))
        latest_by_request[request_key] = entry

    latest = list(latest_by_request.values())
    failed_blocking = sorted({
        entry["tool_name"]
        for entry in latest
        if entry.get("tool_name") in BLOCKING_TOOLS
        and entry.get("status") == STATUS_FAILED
    })
    failed_scoped = sorted({
        entry["tool_name"]
        for entry in latest
        if entry.get("tool_name") not in BLOCKING_TOOLS
        and entry.get("status") == STATUS_FAILED
    })
    invalid_inputs = sorted({
        entry["tool_name"]
        for entry in latest
        if entry.get("status") == STATUS_INVALID_INPUT
    })

    usable_statuses = {STATUS_SUCCESS, STATUS_NORMAL_EMPTY}
    unavailable_core_domains = []
    for domain, tool_names in CORE_DOMAINS.items():
        domain_entries = [
            entry for entry in latest if entry.get("tool_name") in tool_names
        ]
        if domain_entries and not any(
            entry.get("status") in usable_statuses for entry in domain_entries
        ):
            unavailable_core_domains.append(domain)

    failed_tools = failed_blocking + failed_scoped
    claim_constraints = [
        TOOL_CLAIM_CONSTRAINTS[name]
        for name in failed_tools
        if name in TOOL_CLAIM_CONSTRAINTS
    ]

    if not entries or failed_blocking or len(unavailable_core_domains) >= 2:
        confidence = "低"
    elif failed_scoped or unavailable_core_domains or invalid_inputs:
        confidence = "中"
    else:
        confidence = "高"

    return {
        "confidence": confidence,
        "attempt_count": len(entries),
        "latest": latest,
        "status_counts": dict(Counter(entry.get("status") for entry in latest)),
        # 保留旧字段名，兼容已存在的调用方；语义已收窄为“全局基础失败”。
        "failed_critical": failed_blocking,
        "failed_noncritical": failed_scoped,
        "failed_blocking": failed_blocking,
        "failed_scoped": failed_scoped,
        "unavailable_core_domains": unavailable_core_domains,
        "claim_constraints": claim_constraints,
        "invalid_inputs": invalid_inputs,
    }


def format_tool_ledger_summary(summary: dict[str, Any]) -> str:
    """生成给质量门控、报告和持久化结果使用的可审计摘要。"""
    confidence = summary["confidence"]
    lines = [
        "### 数据接口调用台账",
        f"- 调用次数：{summary['attempt_count']}；结论可信度上限：{confidence}",
    ]
    if summary["failed_blocking"]:
        lines.append(
            "- 基础数据失败：" + "、".join(
                _tool_label(name) for name in summary["failed_blocking"]
            )
        )
    if summary["failed_scoped"]:
        lines.append(
            "- 分项数据缺失：" + "、".join(
                _tool_label(name) for name in summary["failed_scoped"]
            )
        )
    if summary["unavailable_core_domains"]:
        lines.append(
            "- 完全不可用的主要领域："
            + "、".join(summary["unavailable_core_domains"])
        )
    if summary["invalid_inputs"]:
        lines.append(
            "- 输入无效：" + "、".join(
                _tool_label(name) for name in summary["invalid_inputs"]
            )
        )
    if not summary["latest"]:
        lines.append("- 未调用任何数据工具，不能验证分析数据。")
        return "\n".join(lines)

    lines.extend(["", "工具 | 最终状态 | 重要性", "--- | --- | ---"])
    for entry in sorted(summary["latest"], key=lambda item: item["tool_name"]):
        importance = "基础" if entry.get("tool_name") in BLOCKING_TOOLS else "分项"
        status = _STATUS_LABELS.get(entry.get("status"), "未知")
        lines.append(f"{_tool_label(entry['tool_name'])} | {status} | {importance}")
    if summary["claim_constraints"]:
        lines.extend(["", "### 本次结论使用限制"])
        lines.extend(f"- {item}。" for item in summary["claim_constraints"])
    return "\n".join(lines)


def format_claim_constraints(summary: dict[str, Any]) -> str:
    """生成供所有下游决策节点执行的简短、确定性证据边界。"""
    confidence = summary["confidence"]
    lines = [f"数据可信度：{confidence}。以下限制是代码层硬约束："]
    constraints = summary.get("claim_constraints", [])
    if not constraints:
        lines.append("- 当前没有因接口失败而新增的结论限制。")
    else:
        lines.extend(f"- {item}。" for item in constraints)
    if confidence == "中":
        lines.append("- 可以综合其他已成功数据给出参考倾向，但必须明确说明缺失项。")
    elif confidence == "低":
        lines.append("- 不得给出买入、卖出、具体价位或投入比例。")
    lines.append("- 不得用新闻、常识或其他间接材料冒充缺失接口的直接证据。")
    return "\n".join(lines)
