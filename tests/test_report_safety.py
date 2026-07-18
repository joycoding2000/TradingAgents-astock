"""Regression tests for user-facing report safety and final signal selection."""

from web.history import extract_signal
from web.pdf_export import generate_markdown
from web.report_safety import DATA_INCOMPLETE_NOTICE


def test_history_uses_final_rating_not_earlier_research_opinion():
    state = {
        "investment_plan": "**Rating**: Hold",
        "trader_investment_decision": "**Rating**: Hold",
        "final_trade_decision": "**Rating**: Sell",
    }

    assert extract_signal(state) == "Sell"


def test_history_preserves_five_tier_final_rating_and_low_quality_override():
    state = {"final_trade_decision": "**Rating**: Underweight"}
    assert extract_signal(state) == "Underweight"

    state["data_quality_status"] = "低"
    assert extract_signal(state) == "DataIncomplete"


def test_low_quality_markdown_hides_actionable_internal_reports(monkeypatch):
    monkeypatch.setattr("web.pdf_export.stock_display_label", lambda ticker, state: ticker)
    monkeypatch.setattr("web.pdf_export.normalize_stock_mentions", lambda text, ticker, state: text)
    state = {
        "data_quality_status": "低",
        "market_report": "建议立刻买入，目标价 100 元。",
        "final_trade_decision": "**Rating**: Sell\n立即卖出，止损价 80 元。",
        "data_quality_summary": "关键数据失败：资金流向",
    }

    markdown = generate_markdown(state, "600879", "2026-07-18", "Sell")

    assert "交易信号**：**数据不完整" in markdown
    assert DATA_INCOMPLETE_NOTICE in markdown
    assert "立即卖出" not in markdown
    assert "目标价 100" not in markdown


def test_normal_markdown_uses_chinese_five_tier_signal(monkeypatch):
    monkeypatch.setattr("web.pdf_export.stock_display_label", lambda ticker, state: ticker)
    markdown = generate_markdown({}, "600879", "2026-07-18", "Underweight")
    assert "交易信号**：**偏向卖出" in markdown


def test_medium_quality_keeps_conclusion_and_exports_scope_limits(monkeypatch):
    monkeypatch.setattr("web.pdf_export.stock_display_label", lambda ticker, state: ticker)
    monkeypatch.setattr("web.pdf_export.normalize_stock_mentions", lambda text, ticker, state: text)
    state = {
        "data_quality_status": "中",
        "data_quality_constraints": "不能判断主力资金流入或流出。",
        "final_trade_decision": "**Rating**: Hold\n结合现有数据暂时持有。",
    }

    markdown = generate_markdown(state, "600879", "2026-07-17", "Hold")

    assert "交易信号**：**持有" in markdown
    assert "结合现有数据暂时持有" in markdown
    assert "不能判断主力资金流入或流出" in markdown
