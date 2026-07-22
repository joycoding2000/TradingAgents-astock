"""Performance ledger, run-local cache, parallel analysts and fast mode."""

from __future__ import annotations

import threading
import time
from typing import Annotated
import operator
import json

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph

from tradingagents.agents.quality_ledger import (
    RunToolCache,
    STATUS_FAILED,
    create_tracked_tool_node,
)
from tradingagents.graph.performance import summarize_performance_ledger
from tradingagents.graph.performance import timed_node


def _tool_state(name: str, call_id: str, **args):
    return {
        "messages": [AIMessage(content="", tool_calls=[{
            "name": name,
            "args": args,
            "id": call_id,
        }])]
    }


class _TrackedToolState(MessagesState):
    tool_execution_ledger: Annotated[list[dict], operator.add]
    performance_ledger: Annotated[list[dict], operator.add]


def _invoke_tool_node(node, state):
    workflow = StateGraph(_TrackedToolState)
    workflow.add_node("tools", node)
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    return workflow.compile().invoke(state)


def test_run_cache_reuses_success_and_marks_ledger_hit():
    calls = 0

    @tool
    def get_news(ticker: str) -> str:
        """Return test news."""
        nonlocal calls
        calls += 1
        return f"{ticker} 新闻数据"

    cache = RunToolCache()
    first_node = create_tracked_tool_node("news", [get_news], cache)
    second_node = create_tracked_tool_node("policy", [get_news], cache)

    first = _invoke_tool_node(
        first_node, _tool_state("get_news", "call-1", ticker="600519")
    )
    second = _invoke_tool_node(
        second_node, _tool_state("get_news", "call-2", ticker="600519")
    )

    assert calls == 1
    assert first["messages"][0].content == second["messages"][0].content
    assert first["tool_execution_ledger"][0]["cache_hit"] is False
    assert second["tool_execution_ledger"][0]["cache_hit"] is True
    assert second["performance_ledger"][0]["kind"] == "tool"


def test_run_cache_never_reuses_failed_result():
    calls = 0

    @tool
    def get_news(ticker: str) -> str:
        """Return a failed data marker."""
        nonlocal calls
        calls += 1
        return "[数据缺失: 新闻数据暂不可用]"

    cache = RunToolCache()
    node = create_tracked_tool_node("news", [get_news], cache)

    first = _invoke_tool_node(
        node, _tool_state("get_news", "call-1", ticker="600519")
    )
    second = _invoke_tool_node(
        node, _tool_state("get_news", "call-2", ticker="600519")
    )

    assert calls == 2
    assert first["tool_execution_ledger"][0]["status"] == STATUS_FAILED
    assert second["tool_execution_ledger"][0]["cache_hit"] is False


def test_tool_exception_keeps_sanitized_failure_timing():
    @tool
    def get_news(ticker: str) -> str:
        """Raise a test-only vendor error."""
        time.sleep(0.01)
        raise RuntimeError("private upstream detail")

    node = create_tracked_tool_node("news", [get_news], RunToolCache())
    result = _invoke_tool_node(
        node, _tool_state("get_news", "call-1", ticker="600519")
    )

    ledger = result["tool_execution_ledger"][0]
    assert ledger["status"] == STATUS_FAILED
    assert ledger["duration_ms"] >= 5
    assert "private upstream detail" not in str(ledger)


def test_performance_summary_exposes_p50_p95_and_cache_hits():
    summary = summarize_performance_ledger([
        {"kind": "run", "duration_ms": 1000},
        {"kind": "model", "duration_ms": 100},
        {"kind": "model", "duration_ms": 300},
        {"kind": "tool", "duration_ms": 20, "cache_hit": False},
        {"kind": "tool", "duration_ms": 5, "cache_hit": True},
        {"kind": "stage", "stage": "market", "duration_ms": 400},
    ])

    assert summary["wall_duration_ms"] == 1000
    assert summary["model_p50_duration_ms"] == 100
    assert summary["model_p95_duration_ms"] == 300
    assert summary["tool_p95_duration_ms"] == 20
    assert summary["cache_hit_count"] == 1
    assert summary["stage_duration_ms"] == {"market": 400}


def test_timed_node_does_not_treat_optional_name_as_runtime_config():
    received = []

    def trader_node(state, name="Trader"):
        received.append(name)
        return {"value": state["value"] + 1}

    wrapped = timed_node("Trader", trader_node, stage="trader")
    result = wrapped({"value": 1}, {"recursion_limit": 100})

    assert received == ["Trader"]
    assert result["value"] == 2


def test_fast_quality_gate_reviews_only_enabled_reports():
    from tradingagents.agents.quality_gate import create_quality_gate

    prompts = []

    class _LLM:
        def invoke(self, prompt):
            prompts.append(prompt)
            return type("Response", (), {"content": "三份报告均可用"})()

    report = "| 指标 | 值 |\n|---|---|\n| 示例 | 1 |\n" + "分析内容" * 80
    state = {
        "company_of_interest": "600519",
        "trade_date": "2026-07-17",
        "analysis_mode": "fast",
        "selected_analysts": ["market", "news", "fundamentals"],
        "market_report": report,
        "news_report": report,
        "fundamentals_report": report,
        "tool_execution_ledger": [
            {"tool_name": "get_stock_data", "status": "success"},
            {"tool_name": "get_indicators", "status": "success"},
            {"tool_name": "get_fundamentals", "status": "success"},
            {"tool_name": "get_balance_sheet", "status": "success"},
            {"tool_name": "get_cashflow", "status": "success"},
            {"tool_name": "get_income_statement", "status": "success"},
            {"tool_name": "get_profit_forecast", "status": "success"},
            {"tool_name": "get_industry_comparison", "status": "success"},
            {"tool_name": "get_news", "status": "success"},
            {"tool_name": "get_global_news", "status": "success"},
        ],
    }

    result = create_quality_gate(_LLM())(state)

    assert len(prompts) == 1
    assert "以下是 3 位分析师" in prompts[0]
    assert "### 情绪分析师" not in prompts[0]
    assert result["data_quality_status"] == "高"
    assert result["data_completeness_status"] == "complete"
    assert result["report_confidence_score"] == 4
    assert "三项速览" in result["data_quality_summary"]
    assert "不得声称已全面核验" in result["data_quality_constraints"]


def test_fast_mode_is_saved_in_history_and_markdown(tmp_path, monkeypatch):
    from web import history
    from web.pdf_export import generate_markdown

    logs = tmp_path / "logs"
    log_dir = logs / "600879" / "TradingAgentsStrategy_logs"
    log_dir.mkdir(parents=True)
    saved_state = {
        "analysis_mode": "fast",
        "data_quality_status": "低",
        "data_quality_summary": "",
        "final_trade_decision": "",
    }
    log_path = log_dir / "full_states_log_2026-07-17.json"
    log_path.write_text(json.dumps(saved_state), encoding="utf-8")
    monkeypatch.setattr(history, "_results_dir", lambda: logs)
    monkeypatch.setattr(
        "web.pdf_export.stock_display_label", lambda ticker, state: ticker
    )

    entries = history.get_history(include_mode=True)
    markdown = generate_markdown(
        saved_state, "600879", "2026-07-17", "DataIncomplete"
    )

    assert entries[0]["analysis_mode"] == "fast"
    assert "**分析范围**：三项速览" in markdown
    assert "**数据状态**：关键数据缺失" in markdown


def test_selected_analyst_branches_start_in_parallel_and_join(monkeypatch):
    from tradingagents.graph import setup as setup_module
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.graph.propagation import Propagator
    from tradingagents.graph.setup import GraphSetup

    starts: dict[str, float] = {}
    start_lock = threading.Lock()
    report_fields = {
        "market": "market_report",
        "news": "news_report",
        "fundamentals": "fundamentals_report",
    }

    def analyst_factory(analyst: str):
        def factory(llm):
            def node(state):
                with start_lock:
                    starts[analyst] = time.perf_counter()
                time.sleep(0.12)
                return {
                    "messages": [AIMessage(content=f"{analyst} done")],
                    report_fields[analyst]: f"{analyst} report",
                }
            return node
        return factory

    monkeypatch.setattr(setup_module, "create_market_analyst", analyst_factory("market"))
    monkeypatch.setattr(setup_module, "create_news_analyst", analyst_factory("news"))
    monkeypatch.setattr(
        setup_module,
        "create_fundamentals_analyst",
        analyst_factory("fundamentals"),
    )

    def quality_factory(llm):
        return lambda state: {
            "data_quality_summary": "ok",
            "data_quality_status": "高",
            "data_quality_constraints": "none",
        }

    def debate_node(speaker: str):
        def node(state):
            current = state["investment_debate_state"]
            count = current["count"] + 1
            return {"investment_debate_state": {
                **current,
                "current_response": f"{speaker} response",
                "count": count,
            }}
        return node

    def manager_factory(llm):
        def node(state):
            debate = state["investment_debate_state"]
            return {
                "investment_debate_state": {**debate, "judge_decision": "plan"},
                "investment_plan": "plan",
            }
        return node

    def trader_factory(llm):
        return lambda state: {"trader_investment_plan": "trade"}

    def risk_node(speaker: str):
        def node(state):
            current = state["risk_debate_state"]
            return {"risk_debate_state": {
                **current,
                "latest_speaker": speaker,
                "count": current["count"] + 1,
            }}
        return node

    def pm_factory(llm):
        def node(state):
            risk = state["risk_debate_state"]
            return {
                "risk_debate_state": {**risk, "judge_decision": "final"},
                "final_trade_decision": "final",
            }
        return node

    monkeypatch.setattr(setup_module, "create_quality_gate", quality_factory)
    monkeypatch.setattr(setup_module, "create_bull_researcher", lambda llm: debate_node("Bull"))
    monkeypatch.setattr(setup_module, "create_bear_researcher", lambda llm: debate_node("Bear"))
    monkeypatch.setattr(setup_module, "create_research_manager", manager_factory)
    monkeypatch.setattr(setup_module, "create_trader", trader_factory)
    monkeypatch.setattr(setup_module, "create_aggressive_debator", lambda llm: risk_node("Aggressive"))
    monkeypatch.setattr(setup_module, "create_conservative_debator", lambda llm: risk_node("Conservative"))
    monkeypatch.setattr(setup_module, "create_neutral_debator", lambda llm: risk_node("Neutral"))
    monkeypatch.setattr(setup_module, "create_portfolio_manager", pm_factory)

    selected = ["market", "news", "fundamentals"]
    graph_setup = GraphSetup(
        None,
        None,
        ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1),
        snapshot_node=lambda state: {
            "data_snapshot": {
                "ticker": state["company_of_interest"],
                "trade_date": state["trade_date"],
                "records": [],
            }
        },
    )
    graph = graph_setup.setup_graph(selected).compile()
    initial = Propagator().create_initial_state(
        "600519",
        "2026-07-17",
        analysis_mode="fast",
        selected_analysts=selected,
    )

    result = graph.invoke(initial, config={"recursion_limit": 100})

    assert result["market_report"] == "market report"
    assert result["news_report"] == "news report"
    assert result["fundamentals_report"] == "fundamentals report"
    assert max(starts.values()) - min(starts.values()) < 0.08
    analyst_stages = {
        entry["stage"] for entry in result["performance_ledger"]
        if entry.get("kind") == "stage" and entry.get("stage") in selected
    }
    assert analyst_stages == set(selected)
