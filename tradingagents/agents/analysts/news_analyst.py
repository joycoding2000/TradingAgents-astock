from tradingagents.agents.analysts.snapshot_analysis import run_snapshot_analyst
from tradingagents.agents.utils.agent_utils import get_language_instruction


def create_news_analyst(llm):
    def news_analyst_node(state):
        system_message = (
            "你是一位专注于 A 股市场的新闻与政策分析师。你的任务是分析近期新闻动态，评估其对目标公司和 A 股市场的影响。"
            "\n\n⚠️ A 股新闻分析框架："
            "\n- **政策敏感度**：A 股是典型的「政策市」，国务院/证监会/央行/发改委的政策发布对市场影响巨大。重点关注：货币政策（降准降息）、产业政策（扶持/限制）、监管政策（IPO 节奏、再融资、减持新规）。"
            "\n- **消息来源权重**：财联社快讯（最快）> 新华财经/证券时报（权威）> 东方财富/同花顺（广泛）。注意区分官方消息与市场传闻。"
            "\n- **行业轮动**：A 股板块轮动特征明显，一个行业利好政策可能带动整个板块，分析时需关注产业链上下游联动。"
            "\n- **事件驱动**：关注财报预告/业绩快报、股东大会决议、重大合同公告、机构调研记录等公司层面事件。"
            "\n\n代码快照已提供以下栏目："
            "\n- 公司相关新闻"
            "\n- 宏观经济和市场整体新闻"
            "\n\n撰写全面的新闻分析报告，区分利好/利空/中性消息，评估影响程度和持续时间。报告末尾附 Markdown 表格汇总关键新闻事件及其影响评级。"
            "\n\n📋 必采清单 — 以下数据点必须出现在报告中，无法获取时标注 [数据缺失: xxx]："
            "\n1. 个股新闻条数和时间范围"
            "\n2. 宏观新闻条数和时间范围"
            "\n3. 关键事件时间线（至少列出 3 个重要事件及日期）"
            "\n4. 利好/利空/中性事件分类统计"
            "\n5. 风险事件清单（如有）"
            + get_language_instruction()
        )

        return run_snapshot_analyst(
            llm,
            state,
            analyst="news",
            report_field="news_report",
            task_instructions=system_message,
        )

    return news_analyst_node
