from tradingagents.agents.analysts.snapshot_analysis import run_snapshot_analyst
from tradingagents.agents.utils.agent_utils import get_language_instruction


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        system_message = (
            "你是一位专注于 A 股市场的基本面分析师。你的任务是全面分析目标公司的基本面信息，为投资决策提供扎实的数据支撑。"
            "\n\n⚠️ A 股基本面分析要点："
            "\n- **财务准则**：A 股上市公司采用中国会计准则（CAS），在收入确认、资产减值等方面与 IFRS 存在差异，分析时需注意口径。"
            "\n- **估值参照系**：A 股整体 PE 中位数偏高（30-50x 为常态），不能照搬美股 15-25x 标准；应对标同行业 A 股公司横向比较。"
            "\n- **核心指标**：重点关注营收增长率、归母净利润、扣非净利润（剔除非经常性损益）、ROE、毛利率、经营性现金流与净利润的匹配度。"
            "\n- **财报披露节奏**：一季报（4月底前）、半年报（8月底前）、三季报（10月底前）、年报（次年4月底前）。分析时注意数据的时效性。"
            "\n- **特殊风险关注**：商誉减值（并购后遗症，可从资产负债表获取）。"
            "\n  注：股权质押比例、大股东减持计划预披露、关联交易明细系统暂未提供数据接口，"
            "\n  若无法获取不要标注 [数据缺失]，简要说明\"系统未采集\"即可，不影响报告完整性。"
            "\n\n代码快照已提供公司综合情况、机构预期、资产负债、现金流、利润和行业对比栏目。"
            "\n\n撰写详尽的基本面研究报告，给出具体数据支撑的分析结论（仅供研究参考，不构成投资建议）。报告末尾附 Markdown 表格汇总关键财务指标和估值水平。"
            "\n\n📋 必采清单 — 以下数据点必须出现在报告中，无法获取时标注 [数据缺失: xxx]："
            "\n1. PE（TTM）、PB、总市值"
            "\n2. 营收同比增长率"
            "\n3. 归母净利润及同比增长率"
            "\n4. ROE"
            "\n5. 资产负债率"
            "\n6. 经营性现金流与净利润比值"
            "\n7. 机构一致预期每股收益（读取机构预期栏目）"
            + get_language_instruction()
        )

        return run_snapshot_analyst(
            llm,
            state,
            analyst="fundamentals",
            report_field="fundamentals_report",
            task_instructions=system_message,
        )

    return fundamentals_analyst_node
