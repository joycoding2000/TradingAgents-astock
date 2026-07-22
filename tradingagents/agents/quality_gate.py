from typing import Annotated

from tradingagents.agents.quality_ledger import (
    expected_tools_for_analysts,
    format_claim_constraints,
    format_tool_ledger_summary,
    summarize_tool_ledger,
)

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
    "获取失败",
    "查询失败",
    "Error fetching",
    "I cannot retrieve",
    "I don't have access",
    "unable to fetch",
    "工具调用失败",
]


def _product_quality_fields(
    confidence: str,
    analysis_mode: str,
    selected_analysts: list[str],
) -> dict[str, object]:
    """生成供网页、历史列表和导出统一使用的通俗质量字段。"""
    data_status = {
        "高": "complete",
        "中": "partial",
        "低": "critical_missing",
    }.get(confidence, "unknown")
    full_scope = (
        analysis_mode == "full"
        and set(selected_analysts) == set(REPORT_FIELDS)
    )
    if confidence == "高":
        score = 5 if full_scope else 4
    elif confidence == "中":
        score = 3 if full_scope else 2
    elif confidence == "低":
        score = 1
    else:
        score = 0
    return {
        "data_completeness_status": data_status,
        "report_confidence_score": score,
    }


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
    reports: dict,
    hard_results: dict,
    trade_date: str,
    ticker: str,
    tool_ledger_summary: str = "",
    selected_analysts: list[str] | None = None,
) -> str:
    """Build the LLM review prompt.

    v0.2.22: 把硬检查结果（客观缺失清单）喂给 LLM，让 LLM 在已知硬检查事实的
    基础上判断缺失项是否必采关键项，给出与硬检查一致的最终评级，消除 C vs A 矛盾。
    """
    enabled = selected_analysts or list(REPORT_FIELDS)
    report_sections = []
    for analyst_type in enabled:
        field = REPORT_FIELDS[analyst_type]
        name = ANALYST_NAMES[analyst_type]
        content = reports.get(field, "（未运行）")
        if not content:
            content = "（报告为空）"
        if len(content) > 3000:
            content = content[:3000] + "\n... (truncated for review)"
        report_sections.append(f"### {name} ({analyst_type})\n{content}")

    all_reports = "\n\n".join(report_sections)

    hard_lines = []
    for analyst_type in enabled:
        grade, detail = hard_results[analyst_type]
        name = ANALYST_NAMES[analyst_type]
        hard_lines.append(f"- {name}: [{grade}] {detail}")
    hard_summary = "\n".join(hard_lines)

    review_rows = "\n".join(
        f"| {ANALYST_NAMES[analyst_type]} | A/B/C/D/F | 是否匹配交易日 | "
        "列出缺失的必采项 | 简要说明 |"
        for analyst_type in enabled
    )

    return f"""你是数据质量审核员。以下是 {len(enabled)} 位分析师对 {ticker} 在 {trade_date} 的研究报告。请逐一审核。

## 硬检查结果（代码层客观事实，供参考，非最终评级）
{hard_summary}

## 数据接口调用台账（代码层客观事实，优先级高于报告措辞）
{tool_ledger_summary or "未提供台账"}

---

{all_reports}

---

请按以下格式输出审核结果（不要输出其他内容）：

## 数据质量审核报告

**标的**: {ticker} | **日期**: {trade_date}

| 分析师 | 评级 | 数据时效 | 缺失项 | 备注 |
|--------|------|----------|--------|------|
{review_rows}

**整体评级**: A/B/C/D/F
**数据可信度**: 高/中/低
**建议**: （如有数据缺失，提醒辩论阶段谨慎使用该报告）

评级标准：
- A: 必采清单全部覆盖，数据时效匹配，有汇总表格。非必采的"特殊风险"项缺失（如股权质押/关联交易等系统未提供接口的项）不影响 A 级
- B: 缺少少量分项数据，整体仍可用，但必须限制对应领域结论
- C: 缺少 3+ 项**必采关键**数据或有数据时效问题，需谨慎使用
- D: 大量缺失或主要为失败信息，可信度低
- F: 报告为空或完全无效

重要：硬检查已列出各分析师的客观缺失清单。请判断每处缺失是否属于**必采关键项**：
- 若缺失的是非必采项（系统未提供接口的特殊风险项、或正常空结果如"近30日未上龙虎榜"），不应据此降级
- 若你的评级与硬检查 grade 不一致，需在备注说明理由
- 若台账列出“基础数据失败”，整体数据可信度必须为“低”
- 若台账列出“分项数据缺失”，整体数据可信度不得为“高”；不得使用缺失领域作为结论依据
- 资金流向或行业对比单独/同时失败，不代表其他成功数据失效；通常应判“中”而非“低”
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
        selected_analysts = [
            analyst for analyst in state.get("selected_analysts", REPORT_FIELDS)
            if analyst in REPORT_FIELDS
        ] or list(REPORT_FIELDS)
        analysis_mode = state.get("analysis_mode", "full")

        reports = {}
        for analyst_type in selected_analysts:
            field = REPORT_FIELDS[analyst_type]
            reports[field] = state.get(field, "")

        hard_results = {}
        for analyst_type in selected_analysts:
            field = REPORT_FIELDS[analyst_type]
            grade, detail = _hard_check_report(analyst_type, reports[field])
            hard_results[analyst_type] = (grade, detail)

        hard_summary_lines = []
        for analyst_type, (grade, detail) in hard_results.items():
            name = ANALYST_NAMES[analyst_type]
            hard_summary_lines.append(f"- {name}: [{grade}] {detail}")
        hard_summary = "\n".join(hard_summary_lines)

        expected_tools = expected_tools_for_analysts(selected_analysts)
        tool_summary = summarize_tool_ledger(
            state.get("tool_execution_ledger", []),
            expected_tools=expected_tools,
        )
        tool_ledger_text = format_tool_ledger_summary(tool_summary)
        data_quality_constraints = format_claim_constraints(tool_summary)
        omitted_analysts = [
            ANALYST_NAMES[analyst]
            for analyst in REPORT_FIELDS
            if analyst not in selected_analysts
        ]
        if omitted_analysts:
            data_quality_constraints += (
                "\n- 本次未运行" + "、".join(omitted_analysts) + "；"
                "不得声称已全面核验这些领域，也不得把未覆盖误写为没有风险。"
            )

        fail_count = sum(
            1 for _, (g, _) in hard_results.items() if g in ("F", "D")
        )

        llm_review = ""
        if fail_count < 4:
            try:
                review_prompt = _build_review_prompt(
                    reports,
                    hard_results,
                    trade_date,
                    ticker,
                    tool_ledger_text,
                    selected_analysts,
                )
                response = llm.invoke(review_prompt)
                llm_review = response.content
            except Exception as e:
                llm_review = f"（LLM 复审失败: {type(e).__name__}）"

        confidence = tool_summary["confidence"]
        confidence_constraint = ""
        if confidence == "低":
            confidence_constraint = (
                "\n> **代码层限制：基础行情失败、多个主要领域不可用，或未调用数据工具。**"
                "本次结论可信度已被限制为“低”，不得据此直接买卖。\n"
            )
        elif confidence == "中":
            confidence_constraint = (
                "\n> **代码层提示：存在分项数据缺失、单个主要领域不可用或工具输入无效。**"
                "仍可综合成功数据，但不得使用缺失领域作为结论依据。\n"
            )

        if analysis_mode == "fast":
            scope_label = "三项速览（技术、新闻、基本面）"
        elif len(selected_analysts) == len(REPORT_FIELDS):
            scope_label = "七项分析（七个研究角度）"
        else:
            scope_label = f"自选分析（{len(selected_analysts)} 个研究角度）"

        product_fields = _product_quality_fields(
            confidence,
            analysis_mode,
            selected_analysts,
        )

        summary = (
            f"## 数据质量门控结果\n\n"
            f"**标的**: {ticker} | **交易日**: {trade_date}\n\n"
            f"**分析范围**: {scope_label}\n\n"
            f"> 硬检查为代码层客观事实清单（长度/表格/失败标记/缺失项计数），"
            f"LLM 复审为最终评级（综合缺失项是否必采关键）。v0.2.22 起硬检查不再"
            f"机械因 `[数据缺失]` 数量判 C，两层标准统一由 LLM 复审收口。\n\n"
            f"{tool_ledger_text}\n"
            f"\n### 下游结论硬约束\n{data_quality_constraints}\n"
            f"{confidence_constraint}\n"
            f"### 硬检查结果\n{hard_summary}\n\n"
            f"### LLM 复审（最终评级）\n"
            f"{llm_review if llm_review else '（跳过 — 多数报告未通过硬检查）'}\n"
        )

        return {
            "data_quality_summary": summary,
            "data_quality_status": confidence,
            "data_quality_constraints": data_quality_constraints,
            **product_fields,
        }

    return quality_gate_node
