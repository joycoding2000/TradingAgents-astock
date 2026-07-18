# TradingAgents/graph/propagation.py

from typing import Dict, Any, List, Optional
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        past_context: str = "",
        analysis_mode: str = "full",
        selected_analysts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create the initial state for the agent graph."""
        analyst_messages = {
            f"{name}_messages": [("human", company_name)]
            for name in (
                "market", "social", "news", "fundamentals", "policy",
                "hot_money", "lockup",
            )
        }
        return {
            "messages": [("human", company_name)],
            **analyst_messages,
            "company_of_interest": company_name,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "analysis_mode": analysis_mode,
            "selected_analysts": list(selected_analysts or []),
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
            "policy_report": "",
            "hot_money_report": "",
            "lockup_report": "",
            "data_quality_summary": "",
            "data_quality_status": "",
            "data_quality_constraints": "",
            "tool_execution_ledger": [],
            "performance_ledger": [],
            "performance_summary": {},
        }

    def get_graph_args(self, callbacks: Optional[List] = None) -> Dict[str, Any]:
        """Get arguments for the graph invocation.

        Args:
            callbacks: Optional list of callback handlers for tool execution tracking.
                       Note: LLM callbacks are handled separately via LLM constructor.
        """
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
