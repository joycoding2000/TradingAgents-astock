"""Deterministic data snapshot collection and analyst isolation tests."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from tradingagents.agents.data_snapshot import (
    build_snapshot_requests,
    collect_data_snapshot,
    render_snapshot_for_analyst,
)
from tradingagents.agents.quality_ledger import STATUS_FAILED, STATUS_NORMAL_EMPTY
from tradingagents.agents.quality_ledger import expected_tools_for_analysts
from tradingagents.agents.analysts.market_analyst import create_market_analyst


FAST_ANALYSTS = ["market", "news", "fundamentals"]
FULL_ANALYSTS = [
    "market", "social", "news", "fundamentals", "policy", "hot_money", "lockup",
]


def test_fast_snapshot_plan_is_fixed_and_complete():
    requests = build_snapshot_requests("600519", "2026-07-17", FAST_ANALYSTS)

    assert len(requests) == 17
    assert len({request.tool_name for request in requests}) == 10
    assert sum(request.tool_name == "get_indicators" for request in requests) == 8
    assert all(request.args for request in requests)


def test_full_snapshot_plan_covers_all_seventeen_tool_types():
    requests = build_snapshot_requests("600519", "2026-07-17", FULL_ANALYSTS)

    planned_tools = {request.tool_name for request in requests}
    assert planned_tools == expected_tools_for_analysts(FULL_ANALYSTS)
    assert len(planned_tools) == 17
    assert len(requests) == 24


def test_snapshot_plan_fails_loudly_when_required_tool_has_no_request(monkeypatch):
    from tradingagents.agents import data_snapshot

    monkeypatch.setitem(
        data_snapshot.ANALYST_EXPECTED_TOOLS,
        "future_analyst",
        {"get_future_required_data"},
    )

    try:
        build_snapshot_requests("600519", "2026-07-17", ["future_analyst"])
    except RuntimeError as exc:
        assert "get_future_required_data" in str(exc)
    else:  # pragma: no cover - the invariant must never be bypassed
        raise AssertionError("missing snapshot requests must fail before analysis")


def test_snapshot_executes_every_planned_request_once_and_sanitizes_failures():
    requests = build_snapshot_requests("600519", "2026-07-17", FULL_ANALYSTS)
    calls: list[tuple[str, dict]] = []

    def fake_tool(tool_name):
        def invoke(**kwargs):
            calls.append((tool_name, kwargs))
            if tool_name == "get_fund_flow":
                return "[数据缺失: 个股主力资金数据暂不可用]"
            if tool_name == "get_dragon_tiger_board":
                return "近30日未上龙虎榜。"
            return f"{tool_name} 数据"
        return invoke

    registry = {
        request.tool_name: fake_tool(request.tool_name)
        for request in requests
    }
    result = collect_data_snapshot(
        "600519",
        "2026-07-17",
        FULL_ANALYSTS,
        tool_registry=registry,
        clock=lambda: "2026-07-18T00:00:00+00:00",
    )

    snapshot = result["data_snapshot"]
    assert len(calls) == len(requests)
    assert snapshot["schema_version"] == 1
    assert len(snapshot["snapshot_id"]) == 16
    assert snapshot["request_count"] == 24
    assert snapshot["started_at"] == "2026-07-18T00:00:00+00:00"
    failed = next(
        record for record in snapshot["records"]
        if record["tool_name"] == "get_fund_flow"
    )
    empty = next(
        record for record in snapshot["records"]
        if record["tool_name"] == "get_dragon_tiger_board"
    )
    assert failed["status"] == STATUS_FAILED
    assert failed["content"] == ""
    assert empty["status"] == STATUS_NORMAL_EMPTY
    assert empty["content"]
    assert all("args" not in record for record in snapshot["records"])
    assert len(result["tool_execution_ledger"]) == 24


def test_analyst_receives_only_its_snapshot_subset_and_has_no_tools():
    prompts = []

    class FakeLLM:
        def invoke(self, prompt):
            prompts.append(prompt)
            return AIMessage(content="| 数据 | 结论 |\n|---|---|\n| 快照 | 可用 |" + "分析" * 100)

        def bind_tools(self, tools):  # pragma: no cover - must never be called
            raise AssertionError("snapshot analysts must not bind tools")

    state = {
        "company_of_interest": "600519",
        "trade_date": "2026-07-17",
        "data_snapshot": {
            "ticker": "600519",
            "trade_date": "2026-07-17",
            "completed_at": "2026-07-18T00:00:00+00:00",
            "records": [
                {
                    "label": "股价和成交量",
                    "tool_name": "get_stock_data",
                    "audiences": ["market"],
                    "status": "success",
                    "content": "收盘价 1500 元",
                },
                {
                    "label": "公司基本情况",
                    "tool_name": "get_fundamentals",
                    "audiences": ["fundamentals"],
                    "status": "success",
                    "content": "市盈率 20 倍",
                },
            ],
        },
    }

    result = create_market_analyst(FakeLLM())(state)

    assert result["market_report"]
    assert len(prompts) == 1
    assert "收盘价 1500 元" in prompts[0]
    assert "市盈率 20 倍" not in prompts[0]
    assert "你没有任何数据工具" in prompts[0]


def test_render_snapshot_marks_failed_record_as_missing():
    text = render_snapshot_for_analyst({
        "ticker": "600879",
        "trade_date": "2026-07-17",
        "completed_at": "2026-07-18T00:00:00+00:00",
        "records": [{
            "label": "资金流向",
            "audiences": ["hot_money"],
            "status": "failed",
            "content": "",
        }],
    }, "hot_money")

    assert "[数据缺失：资金流向未获取]" in text
