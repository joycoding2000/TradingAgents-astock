"""Regression tests for the low-friction A-share Web experience."""

import pytest

from tradingagents.dataflows import a_stock
from web.components.sidebar import _resolve_user_input
from web.plain_language import make_conclusion_plain


def test_resolve_ticker_accepts_pinyin_initials(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_build_name_code_map",
        lambda: ({"贵州茅台": "600519", "宁德时代": "300750"}, {}),
    )

    assert a_stock.resolve_ticker("gzmt") == "600519"
    assert a_stock.resolve_ticker("NDSD") == "300750"


def test_resolve_ticker_reports_ambiguous_initials(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_build_name_code_map",
        lambda: ({"中国平安": "601318", "中国平煤": "601666"}, {}),
    )

    assert a_stock.resolve_ticker("zgpa") == "601318"

    monkeypatch.setattr(
        a_stock,
        "_build_name_code_map",
        lambda: ({"华夏银行": "600015", "华兴银行": "000001"}, {}),
    )
    with pytest.raises(ValueError) as exc_info:
        a_stock.resolve_ticker("hxyh")
    assert "匹配到多只股票" in str(exc_info.value)


def test_web_rejects_unknown_shorthand_but_core_resolver_keeps_foreign_symbol(monkeypatch):
    monkeypatch.setattr(a_stock, "_build_name_code_map", lambda: ({}, {}))

    assert a_stock.resolve_ticker("SPY") == "SPY"
    code, error = _resolve_user_input("unknown")
    assert code == ""
    assert error and "找不到简拼" in error


def test_plain_conclusion_translates_labels_ratings_and_jargon():
    text = (
        "**Rating**: Overweight\n\n"
        "**Executive Summary**: Use 5% position sizing and set a stop-loss. "
        "PE is high; watch MACD and capital flow."
    )

    result = make_conclusion_plain(text)

    assert "**最终建议**: 偏向买入" in result
    assert "**具体做法**" in result
    assert "投入资金比例" in result
    assert "亏损控制价" in result
    assert "市盈率" in result
    assert "价格走势指标" in result
    assert "资金流向" in result


def test_plain_conclusion_explains_common_a_share_terms_from_live_output():
    text = "五十日均线、毛利率、现金流、高开低走、缩量回踩后企稳，T+1规则下不要满仓，市盈率偏低。"

    result = make_conclusion_plain(text)

    assert "近50个交易日的平均价格" in result
    assert "卖货后能留下的钱占比" in result
    assert "公司手头现金进出情况" in result
    assert "开盘涨、收盘跌" in result
    assert "成交量变小" in result
    assert "价格回落再试探" in result
    assert "不再继续下跌并站稳" in result
    assert "当天买入、下个交易日才能卖出规则" in result
    assert "把大部分钱都投进去" in result
    assert "股价和公司赚钱能力的比值" in result
