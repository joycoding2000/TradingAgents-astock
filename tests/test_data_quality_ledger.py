"""v0.2.23：数据工具台账、可信度上限与结果持久化回归。"""

import json

from tradingagents.agents.quality_ledger import (
    STATUS_FAILED,
    STATUS_NORMAL_EMPTY,
    STATUS_SUCCESS,
    build_tool_ledger,
    format_tool_ledger_summary,
    summarize_tool_ledger,
)


class _ToolMessage:
    def __init__(self, tool_call_id, content, status="success"):
        self.tool_call_id = tool_call_id
        self.content = content
        self.status = status


def test_tool_ledger_classifies_success_normal_empty_and_failure():
    calls = [
        {"id": "1", "name": "get_stock_data"},
        {"id": "2", "name": "get_dragon_tiger_board"},
        {"id": "3", "name": "get_fund_flow"},
    ]
    messages = [
        _ToolMessage("1", "日期 | 收盘价\n--- | ---\n2026-07-17 | 100"),
        _ToolMessage("2", "近30日未上龙虎榜。"),
        _ToolMessage("3", "[数据缺失: 个股主力资金数据暂不可用]"),
    ]

    ledger = build_tool_ledger("hot_money", calls, messages)

    assert [entry["status"] for entry in ledger] == [
        STATUS_SUCCESS,
        STATUS_NORMAL_EMPTY,
        STATUS_FAILED,
    ]
    assert all("content" not in entry for entry in ledger)
    assert all(len(entry["request_key"]) == 16 for entry in ledger)
    assert ledger[2]["critical"] is False
    assert ledger[2]["impact"] == "分项"


def test_tracked_tool_node_records_real_toolnode_output():
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from langgraph.graph import END, START, MessagesState, StateGraph
    from tradingagents.agents.quality_ledger import create_tracked_tool_node

    @tool
    def get_stock_data() -> str:
        """Return a minimal valid stock-data response."""
        return "日期 | 收盘价\n--- | ---\n2026-07-17 | 100"

    class _ToolState(MessagesState):
        tool_execution_ledger: list[dict]

    workflow = StateGraph(_ToolState)
    workflow.add_node("tools", create_tracked_tool_node("market", [get_stock_data]))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    result = workflow.compile().invoke({
        "messages": [AIMessage(content="", tool_calls=[{
            "name": "get_stock_data", "args": {}, "id": "call-1",
        }])]
    })

    assert result["messages"][-1].content.startswith("日期")
    ledger = result["tool_execution_ledger"]
    assert ledger[0]["tool_name"] == "get_stock_data"
    assert ledger[0]["analyst"] == "market"
    assert ledger[0]["status"] == STATUS_SUCCESS
    assert ledger[0]["critical"] is True
    assert ledger[0]["tool_call_id"] == "call-1"
    assert len(ledger[0]["request_key"]) == 16


def test_ledger_latest_success_overrides_a_retried_failure():
    ledger = [
        {"tool_name": "get_fund_flow", "status": STATUS_FAILED, "critical": True, "request_key": "same-request"},
        {"tool_name": "get_fund_flow", "status": STATUS_SUCCESS, "critical": True, "request_key": "same-request"},
    ]

    summary = summarize_tool_ledger(ledger)

    assert summary["confidence"] == "高"
    assert summary["failed_critical"] == []


def test_ledger_different_requests_keep_partial_failure_as_medium():
    summary = summarize_tool_ledger([
        {"tool_name": "get_news", "status": STATUS_FAILED, "critical": True, "request_key": "news-a"},
        {"tool_name": "get_news", "status": STATUS_SUCCESS, "critical": True, "request_key": "news-b"},
    ])

    assert summary["confidence"] == "中"
    assert summary["failed_scoped"] == ["get_news"]


def test_expected_but_never_called_tool_is_not_misreported_as_complete():
    summary = summarize_tool_ledger(
        [{"tool_name": "get_stock_data", "status": STATUS_SUCCESS}],
        expected_tools={"get_stock_data", "get_indicators"},
    )

    assert summary["confidence"] == "中"
    assert summary["missing_tools"] == ["get_indicators"]
    assert "技术指标 | 未获取 | 分项" in format_tool_ledger_summary(summary)


def test_expected_stock_data_not_called_blocks_reliable_conclusion():
    summary = summarize_tool_ledger(
        [{"tool_name": "get_news", "status": STATUS_SUCCESS}],
        expected_tools={"get_stock_data", "get_news"},
    )

    assert summary["confidence"] == "低"
    assert summary["missing_blocking"] == ["get_stock_data"]


def test_ledger_critical_failure_caps_confidence_and_is_auditable():
    summary = summarize_tool_ledger([
        {"tool_name": "get_stock_data", "status": STATUS_FAILED, "critical": True},
        {"tool_name": "get_dragon_tiger_board", "status": STATUS_NORMAL_EMPTY, "critical": False},
    ])

    text = format_tool_ledger_summary(summary)

    assert summary["confidence"] == "低"
    assert summary["failed_critical"] == ["get_stock_data"]
    assert "股价和成交量 | 失败 | 基础" in text


def test_fund_flow_and_industry_failures_limit_scopes_without_blocking_report():
    summary = summarize_tool_ledger([
        {"tool_name": "get_stock_data", "status": STATUS_SUCCESS},
        {"tool_name": "get_indicators", "status": STATUS_SUCCESS},
        {"tool_name": "get_fundamentals", "status": STATUS_SUCCESS},
        {"tool_name": "get_news", "status": STATUS_SUCCESS},
        {"tool_name": "get_fund_flow", "status": STATUS_FAILED},
        {"tool_name": "get_industry_comparison", "status": STATUS_FAILED},
    ])

    assert summary["confidence"] == "中"
    assert summary["failed_blocking"] == []
    assert summary["failed_scoped"] == [
        "get_fund_flow", "get_industry_comparison"
    ]
    assert "不能判断主力资金流入、流出、抢筹或出逃" in summary["claim_constraints"]
    assert "不能判断行业排名、行业强弱和板块轮动" in summary["claim_constraints"]


def test_two_unavailable_major_domains_cap_report_at_low_confidence():
    summary = summarize_tool_ledger([
        {"tool_name": "get_stock_data", "status": STATUS_SUCCESS},
        {"tool_name": "get_fundamentals", "status": STATUS_FAILED},
        {"tool_name": "get_balance_sheet", "status": STATUS_FAILED},
        {"tool_name": "get_cashflow", "status": STATUS_FAILED},
        {"tool_name": "get_income_statement", "status": STATUS_FAILED},
        {"tool_name": "get_news", "status": STATUS_FAILED},
        {"tool_name": "get_global_news", "status": STATUS_FAILED},
    ])

    assert summary["confidence"] == "低"
    assert summary["unavailable_core_domains"] == ["公司经营", "新闻与政策"]


def test_quality_gate_uses_ledger_as_code_enforced_low_confidence_cap():
    from tradingagents.agents.quality_gate import REPORT_FIELDS, create_quality_gate

    class _LLM:
        def invoke(self, prompt):
            assert "基础数据失败" in prompt
            return type("Response", (), {"content": "LLM 误判为高可信度"})()

    report = "| 指标 | 值 |\n|---|---|\n| 示例 | 1 |\n" + "分析内容" * 80
    state = {
        "company_of_interest": "600519",
        "trade_date": "2026-07-17",
        **{field: report for field in REPORT_FIELDS.values()},
        "tool_execution_ledger": [
            {"tool_name": "get_stock_data", "status": STATUS_FAILED, "critical": True}
        ],
    }

    result = create_quality_gate(_LLM())(state)

    assert result["data_quality_status"] == "低"
    assert result["data_completeness_status"] == "critical_missing"
    assert result["report_confidence_score"] == 1
    assert "代码层限制：基础行情失败" in result["data_quality_summary"]
    assert "股价和成交量 | 失败 | 基础" in result["data_quality_summary"]
    assert "不得给出买入、卖出、具体价位或投入比例" in result["data_quality_constraints"]


def test_quality_gate_keeps_partial_eastmoney_failures_at_medium():
    from tradingagents.agents.quality_gate import REPORT_FIELDS, create_quality_gate

    class _LLM:
        def invoke(self, prompt):
            assert "资金流向" in prompt
            assert "所属行业情况" in prompt
            return type("Response", (), {"content": "整体评级 B，分项数据受限"})()

    report = "| 指标 | 值 |\n|---|---|\n| 示例 | 1 |\n" + "分析内容" * 80
    state = {
        "company_of_interest": "600879",
        "trade_date": "2026-07-17",
        **{field: report for field in REPORT_FIELDS.values()},
        "tool_execution_ledger": [
            {"tool_name": "get_stock_data", "status": STATUS_SUCCESS},
            {"tool_name": "get_indicators", "status": STATUS_SUCCESS},
            {"tool_name": "get_fundamentals", "status": STATUS_SUCCESS},
            {"tool_name": "get_news", "status": STATUS_SUCCESS},
            {"tool_name": "get_fund_flow", "status": STATUS_FAILED},
            {"tool_name": "get_industry_comparison", "status": STATUS_FAILED},
        ],
    }

    result = create_quality_gate(_LLM())(state)

    assert result["data_quality_status"] == "中"
    assert "不能判断主力资金流入、流出、抢筹或出逃" in result["data_quality_constraints"]
    assert "不能判断行业排名、行业强弱和板块轮动" in result["data_quality_constraints"]
    assert "可以综合其他已成功数据给出参考倾向" in result["data_quality_constraints"]


def test_low_confidence_final_decision_gets_code_enforced_notice():
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    state = {"data_quality_status": "低", "final_trade_decision": "建议小仓位观察。"}
    TradingAgentsGraph._apply_data_quality_limit(state)

    assert state["final_trade_decision"].startswith("⚠️ 数据不全")
    assert "建议小仓位观察" in state["final_trade_decision"]


def test_log_state_persists_quality_summary_status_and_ledger(tmp_path):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.log_states_dict = {}
    graph.config = {"results_dir": str(tmp_path)}
    graph.ticker = "600519"
    final_state = {
        "company_of_interest": "600519",
        "trade_date": "2026-07-17",
        "market_report": "m",
        "sentiment_report": "s",
        "news_report": "n",
        "fundamentals_report": "f",
        "policy_report": "p",
        "hot_money_report": "h",
        "lockup_report": "l",
        "data_quality_summary": "台账摘要",
        "data_quality_status": "低",
        "data_completeness_status": "critical_missing",
        "report_confidence_score": 1,
        "data_quality_constraints": "不得判断主力资金",
        "data_snapshot": {
            "snapshot_id": "snapshot-test",
            "records": [{"label": "股价和成交量", "status": "failed"}],
        },
        "decision_validation_status": "blocked_data",
        "validated_decision": {"rating": "", "can_show_action": False},
        "tool_execution_ledger": [{"tool_name": "get_stock_data", "status": "failed"}],
        "investment_debate_state": {
            "bull_history": "", "bear_history": "", "history": "",
            "current_response": "", "judge_decision": "",
        },
        "trader_investment_plan": "", "risk_debate_state": {
            "aggressive_history": "", "conservative_history": "", "neutral_history": "",
            "history": "", "judge_decision": "",
        },
        "investment_plan": "", "final_trade_decision": "",
    }

    graph._log_state("2026-07-17", final_state)

    path = tmp_path / "600519" / "TradingAgentsStrategy_logs" / "full_states_log_2026-07-17.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["data_quality_summary"] == "台账摘要"
    assert saved["data_quality_status"] == "低"
    assert saved["data_completeness_status"] == "critical_missing"
    assert saved["report_confidence_score"] == 1
    assert saved["analysis_completion_status"] == "completed"
    assert saved["data_quality_constraints"] == "不得判断主力资金"
    assert saved["data_snapshot"]["snapshot_id"] == "snapshot-test"
    assert saved["decision_validation_status"] == "blocked_data"
    assert saved["validated_decision"]["can_show_action"] is False
    assert saved["tool_execution_ledger"][0]["status"] == "failed"
