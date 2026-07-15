from typing import Annotated

REPORT_FIELDS = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
    "policy": "policy_report",
    "hot_money": "hot_money_report",
    "lockup": "lockup_report",
}

ANALYST_NAMES = {
    "market": "技术分析师",
    "social": "情绪分析师",
    "news": "新闻分析师",
    "fundamentals": "基本面分析师",
    "policy": "政策分析师",
    "hot_money": "游资追踪师",
    "lockup": "解禁监控师",
}

MIN_REPORT_LENGTH = 200

FAILURE_MARKERS = [
    "无法获取",
    "I cannot retrieve",
    "I don't have access",
    "unable to fetch",
    "工具调用失败",
]


def _hard_check_report(analyst_type: str, report: str) -> tuple:
    """Run hard checks on a single report. Returns (grade, detail)."""
    if not report or not report.strip():
        return ("F", "报告为空")

    length = len(report.strip())
    if length < MIN_REPORT_LENGTH:
        return ("D", f"报告过短 ({length} chars < {MIN_REPORT_LENGTH})")

    failure_count = sum(1 for m in FAILURE_MARKERS if m in report)
    stripped = report
    for m in FAILURE_MARKERS:
        stripped = stripped.replace(m, "")
    if failure_count > 0 and len(stripped.strip()) < MIN_REPORT_LENGTH:
        return ("D", f"报告主要由失败信息构成 ({failure_count} 处)")

    has_table = "|" in report and "---" in report
    missing_count = report.count("[数据缺失")

    issues = []
    if not has_table:
        issues.append("缺少汇总表格")
    if missing_count > 0:
        issues.append(f"{missing_count} 处数据缺失（关键性待 LLM 判断）")

    # v0.2.22: 不再因 [数据缺失] 数量直接判 C。硬检查无法判断缺失项是否在必采清单 /
    # 是否关键，该语义判断交给 LLM 复审。硬检查只负责客观事实：有缺失 -> B（待 LLM
    # 判断关键性后给最终级）。避免"基本面 3 处非必采缺失被判 C、LLM 复审判 A"的矛盾。
    if not has_table or missing_count > 0:
        return ("B", "；".join(issues) if issues else "基本合格")

    return ("A", f"完整 ({length} chars)")


def _build_review_prompt(
    reports: dict, hard_results: dict, trade_date: str, ticker: str
) -> str:
    """Build the LLM review prompt.

    v0.2.22: 把硬检查结果（客观缺失清单）喂给 LLM，让 LLM 在已知硬检查事实的
    基础上判断缺失项是否必采关键项，给出与硬检查一致的最终评级，消除 C vs A 矛盾。
    """
    report_sections = []
    for analyst_type, field in REPORT_FIELDS.items():
        name = ANALYST_NAMES[analyst_type]
        content = reports.get(field, "（未运行）")
        if not content:
            content = "（报告为空）"
        if len(content) > 3000:
            content = content[:3000] + "\n... (truncated for review)"
        report_sections.append(f"### {name} ({analyst_type})\n{content}")

    all_reports = "\n\n".join(report_sections)

    hard_lines = []
    for analyst_type, (grade, detail) in hard_results.items():
        name = ANALYST_NAMES[analyst_type]
        hard_lines.append(f"- {name}: [{grade}] {detail}")
    hard_summary = "\n".join(hard_lines)

    return f"""你是数据质量审核员。以下是 7 位分析师对 {ticker} 在 {trade_date} 的研究报告。请逐一审核。

## 硬检查结果（代码层客观事实，供参考，非最终评级）
{hard_summary}

---

{all_reports}

---

请按以下格式输出审核结果（不要输出其他内容）：

## 数据质量审核报告

**标的**: {ticker} | **日期**: {trade_date}

| 分析师 | 评级 | 数据时效 | 缺失项 | 备注 |
|--------|------|----------|--------|------|
| 技术分析师 | A/B/C/D/F | 是否匹配交易日 | 列出缺失的必采项 | 简要说明 |
| 情绪分析师 | ... | ... | ... | ... |
| 新闻分析师 | ... | ... | ... | ... |
| 基本面分析师 | ... | ... | ... | ... |
| 政策分析师 | ... | ... | ... | ... |
| 游资追踪师 | ... | ... | ... | ... |
| 解禁监控师 | ... | ... | ... | ... |

**整体评级**: A/B/C/D/F
**数据可信度**: 高/中/低
**建议**: （如有数据缺失，提醒辩论阶段谨慎使用该报告）

评级标准：
- A: 必采清单全部覆盖，数据时效匹配，有汇总表格。非必采的"特殊风险"项缺失（如股权质押/关联交易等系统未提供接口的项）不影响 A 级
- B: 缺少 1-2 项非关键数据，整体可用
- C: 缺少 3+ 项**必采关键**数据或有数据时效问题，需谨慎使用
- D: 大量缺失或主要为失败信息，可信度低
- F: 报告为空或完全无效

重要：硬检查已列出各分析师的客观缺失清单。请判断每处缺失是否属于**必采关键项**：
- 若缺失的是非必采项（系统未提供接口的特殊风险项、或正常空结果如"近30日未上龙虎榜"），不应据此降级
- 若你的评级与硬检查 grade 不一致，需在备注说明理由
"""


def create_quality_gate(llm):
    """Factory for the data quality gate node.

    Sits between the last analyst Msg Clear and Bull Researcher.
    Layer 1: hard checks (code). Layer 2: LLM review (one call).
    Writes data_quality_summary to state for downstream consumers.
    """

    def quality_gate_node(state) -> dict:
        trade_date = state["trade_date"]
        ticker = state["company_of_interest"]

        reports = {}
        for analyst_type, field in REPORT_FIELDS.items():
            reports[field] = state.get(field, "")

        hard_results = {}
        for analyst_type, field in REPORT_FIELDS.items():
            grade, detail = _hard_check_report(analyst_type, reports[field])
            hard_results[analyst_type] = (grade, detail)

        hard_summary_lines = []
        for analyst_type, (grade, detail) in hard_results.items():
            name = ANALYST_NAMES[analyst_type]
            hard_summary_lines.append(f"- {name}: [{grade}] {detail}")
        hard_summary = "\n".join(hard_summary_lines)

        fail_count = sum(
            1 for _, (g, _) in hard_results.items() if g in ("F", "D")
        )

        llm_review = ""
        if fail_count < 4:
            try:
                review_prompt = _build_review_prompt(
                    reports, hard_results, trade_date, ticker
                )
                response = llm.invoke(review_prompt)
                llm_review = response.content
            except Exception as e:
                llm_review = f"（LLM 复审失败: {type(e).__name__}: {e}）"

        summary = (
            f"## 数据质量门控结果\n\n"
            f"**标的**: {ticker} | **交易日**: {trade_date}\n\n"
            f"> 硬检查为代码层客观事实清单（长度/表格/失败标记/缺失项计数），"
            f"LLM 复审为最终评级（综合缺失项是否必采关键）。v0.2.22 起硬检查不再"
            f"机械因 `[数据缺失]` 数量判 C，两层标准统一由 LLM 复审收口。\n\n"
            f"### 硬检查结果\n{hard_summary}\n\n"
            f"### LLM 复审（最终评级）\n"
            f"{llm_review if llm_review else '（跳过 — 多数报告未通过硬检查）'}\n"
        )

        return {"data_quality_summary": summary}

    return quality_gate_node
