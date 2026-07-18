"""Make the Web conclusion readable for non-professional A-share users."""

from __future__ import annotations

import re
from typing import Any


_REPLACEMENTS = (
    (r"\bFund Flow\b", "资金流向"),
    (r"\bHistorical Daily\b", "历史每日数据"),
    (r"\bRealtime\b", "实时数据"),
    (r"\bDate\b", "日期"),
    (r"\bClose\b", "收盘时"),
    (r"\bSignal\b", "信号"),
    (r"\bTotal\b", "合计"),
    (r"\bmain\b", "主力"),
    (r"\blarge\b", "大单"),
    (r"\bmid\b", "中单"),
    (r"\bsmall\b", "小单"),
    (r"\bsuper\b", "超大单"),
    (r"\*\*Recommendation\*\*", "**建议**"),
    (r"\*\*Rationale\*\*", "**为什么**"),
    (r"\*\*Strategic Actions\*\*", "**怎么做**"),
    (r"\*\*Rating\*\*", "**最终建议**"),
    (r"\*\*Executive Summary\*\*", "**具体做法**"),
    (r"\*\*Investment Thesis\*\*", "**主要依据**"),
    (r"\*\*Price Target\*\*", "**参考目标价**"),
    (r"\*\*Time Horizon\*\*", "**大致持有时间**"),
    (r"\*\*Action\*\*", "**操作建议**"),
    (r"\*\*Reasoning\*\*", "**原因**"),
    (r"\*\*Entry Price\*\*", "**参考买入价**"),
    (r"\*\*Stop Loss\*\*", "**亏到这个价格就考虑卖出**"),
    (r"\*\*Position Sizing\*\*", "**建议投入资金比例**"),
    (r"\bOverweight\b", "偏向买入"),
    (r"\bUnderweight\b", "偏向卖出"),
    (r"\bBuy\b", "买入"),
    (r"\bHold\b", "先等等"),
    (r"\bSell\b", "卖出"),
    (r"\bPE\b", "市盈率（股价相对赚钱能力高不高）"),
    (r"\bPB\b", "市净率（股价相对净资产贵不贵）"),
    (r"\bPEG\b", "股价与公司增长是否匹配"),
    (r"\bEPS\b", "每股赚的钱"),
    (r"\bROE\b", "公司用自有资金赚钱的能力"),
    (r"\bMACD\b", "价格走势指标"),
    (r"\bRSI\b", "涨跌是否过头的指标"),
    (r"\bKDJ\b", "短期涨跌快慢指标"),
    # Do not use a word boundary here: Chinese text immediately following
    # ``T+1`` is also a Unicode word character, e.g. ``T+1规则``.
    (r"T\+1", "当天买入、下个交易日才能卖出"),
    (r"(?i)stop[- ]?loss", "亏损控制价"),
    (r"(?i)position sizing", "投入资金比例"),
    (r"(?i)capital flow", "资金流向"),
    (r"(?i)lockup expiry", "限售股可以上市卖出的时间"),
    (r"(?i)insider reduction", "公司重要股东减持"),
    (r"(?:50|五十)日均线", "近50个交易日的平均价格"),
)

_PLAIN_CN = (
    ("仓位", "投入资金比例"),
    ("回撤", "价格从高点下跌"),
    ("估值", "股价贵不贵"),
    ("市盈率", "股价和公司赚钱能力的比值"),
    ("市净率", "股价和公司净资产的比值"),
    ("基本面", "公司经营和赚钱情况"),
    ("毛利率", "卖货后能留下的钱占比"),
    ("现金流", "公司手头现金进出情况"),
    ("北向资金", "外资资金动向"),
    ("高开低走", "开盘涨、收盘跌"),
    ("大阴线", "当天明显下跌的走势"),
    ("缩量", "成交量变小"),
    ("回踩", "价格回落再试探"),
    ("企稳", "不再继续下跌并站稳"),
    ("减仓", "少拿一些"),
    ("清仓", "全部卖掉"),
    ("满仓", "把大部分钱都投进去"),
    ("跌停板", "一天跌到最大跌幅"),
    ("多头", "看涨的一方"),
    ("空头", "看跌的一方"),
    ("量价背离", "成交量和价格走势不一致"),
)


def make_conclusion_plain(text: Any) -> str:
    """Translate fixed labels and common jargon without changing the facts."""
    result = str(text or "")
    for term, replacement in _PLAIN_CN:
        result = result.replace(term, replacement)
    for pattern, replacement in _REPLACEMENTS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result
