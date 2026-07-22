from tradingagents.agents.analysts.snapshot_analysis import run_snapshot_analyst
from tradingagents.agents.utils.agent_utils import get_language_instruction


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        system_message = (
            "你是一位专注于 A 股市场的市场情绪分析师。你的任务是通过分析公司相关新闻、市场讨论和公众情绪，判断市场对目标公司的整体态度和情绪走向。"
            "\n\n⚠️ A 股情绪分析框架："
            "\n- **散户情绪权重高**：A 股散户占比超过 60%，市场情绪对股价的短期影响远大于成熟市场。恐慌和贪婪的情绪波动更剧烈。"
            "\n- **舆论阵地**：东方财富股吧、雪球、同花顺社区是 A 股投资者最活跃的讨论平台。分析新闻时注意推断这些平台可能的情绪反应。"
            "\n- **情绪指标**：关注以下情绪信号 - 连续涨停后的追涨情绪、业绩暴雷后的恐慌抛售、机构调研后的预期变化、热门概念炒作的跟风程度。"
            "\n- **反向指标**：当市场情绪一致性过高（极度乐观或极度悲观）时，往往是反转信号。散户一致看多可能是阶段顶部。"
            "\n- **时间维度**：区分短期情绪波动（1-3 天，由单一事件驱动）和中期情绪趋势（1-4 周，由基本面变化驱动）。"
            "\n\n请读取代码预先采集的公司相关新闻，从已有新闻内容中推断市场情绪方向、强度和可能的转折点；快照未提供的网络讨论不得猜测。"
            "\n\n撰写详细的市场情绪分析报告，包含情绪评分（极度悲观/悲观/中性/乐观/极度乐观）和趋势判断。报告末尾附 Markdown 表格汇总情绪信号和结论。"
            "\n\n📋 必采清单 — 以下数据点必须出现在报告中，无法获取时标注 [数据缺失: xxx]："
            "\n1. 新闻检索条数和时间范围"
            "\n2. 正面/负面/中性新闻比例"
            "\n3. 排名前 3 的舆情主题"
            "\n4. 情绪评分（极度悲观/悲观/中性/乐观/极度乐观）"
            "\n5. 情绪趋势变化方向（升温/降温/平稳）"
            + get_language_instruction()
        )

        return run_snapshot_analyst(
            llm,
            state,
            analyst="social",
            report_field="sentiment_report",
            task_instructions=system_message,
        )

    return social_media_analyst_node
