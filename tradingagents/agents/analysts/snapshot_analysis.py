"""Shared invocation path for analysts that only read a pre-collected snapshot."""

from __future__ import annotations

from typing import Any

from tradingagents.agents.data_snapshot import render_snapshot_for_analyst
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)


def run_snapshot_analyst(
    llm: Any,
    state: dict[str, Any],
    *,
    analyst: str,
    report_field: str,
    task_instructions: str,
) -> dict[str, Any]:
    """Ask one analyst to interpret its immutable snapshot subset, without tools."""
    ticker = str(state["company_of_interest"])
    trade_date = str(state["trade_date"])
    snapshot_text = render_snapshot_for_analyst(
        state.get("data_snapshot", {}),
        analyst,
    )
    prompt = f"""你是一名A股研究分析师。你的数据已经由代码统一采集完成。

{build_instrument_context(ticker)}

强制规则：
1. 你没有任何数据工具，也不得请求、补取或假装调用工具。
2. 只能使用下方只读数据快照，不得用记忆、常识或猜测补齐缺失值。
3. 状态为“获取失败”“输入无效”或标注为数据缺失的栏目，只能说明无法判断。
4. “正常无记录”表示接口正常但确实没有相关记录，不属于数据缺失。
5. 不得给出最终买入或卖出指令；只完成本分析角度的事实解释。
6. 报告末尾必须用中文表格汇总采用的数据、结论和限制。

分析日期：{trade_date}

## 本角度任务
{task_instructions}

## 只读数据快照
{snapshot_text}

请直接输出报告，不要描述内部工作流程。{get_language_instruction()}"""
    response = llm.invoke(prompt)
    return {
        "messages": [response],
        report_field: str(getattr(response, "content", response)),
    }
