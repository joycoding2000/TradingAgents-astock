# TradingAgents/graph/setup.py

from datetime import datetime, timezone
from typing import Any, Callable, Dict
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic
from .performance import timed_node


_MESSAGE_FIELDS = {
    "market": "market_messages",
    "social": "social_messages",
    "news": "news_messages",
    "fundamentals": "fundamentals_messages",
    "policy": "policy_messages",
    "hot_money": "hot_money_messages",
    "lockup": "lockup_messages",
}


def _isolated_analyst_node(node: Callable[..., dict], message_field: str):
    """Run an existing analyst against its private parallel message channel."""
    def invoke(state):
        local_state = dict(state)
        local_state["messages"] = state.get(message_field, [])
        outcome = dict(node(local_state) or {})
        messages = outcome.pop("messages", [])
        return {**outcome, "messages": messages, message_field: messages}

    return invoke


def _isolated_tool_node(node: Callable[..., dict], message_field: str):
    """Run ToolNode without exposing another analyst branch's messages."""
    def invoke(state, config=None):
        local_state = dict(state)
        local_state["messages"] = state.get(message_field, [])
        outcome = dict(node(local_state, config) or {})
        messages = outcome.pop("messages", [])
        return {**outcome, "messages": messages, message_field: messages}

    return invoke


def _analyst_router(message_field: str, tools_node: str, done_node: str):
    def route(state):
        messages = state.get(message_field, [])
        if messages and getattr(messages[-1], "tool_calls", None):
            return tools_node
        return done_node

    return route


def _analyst_done_node(analyst: str):
    """Close a branch and record its wall time without summing parallel work."""
    def done(state):
        entries = [
            entry for entry in state.get("performance_ledger", [])
            if entry.get("stage") == analyst and entry.get("kind") in {"node", "tool"}
        ]
        now = datetime.now(timezone.utc)
        starts = []
        for entry in entries:
            try:
                starts.append(datetime.fromisoformat(str(entry.get("started_at"))))
            except (TypeError, ValueError):
                continue
        started = min(starts) if starts else now
        return {
            "performance_ledger": [{
                "kind": "stage",
                "name": analyst,
                "stage": analyst,
                "status": "success",
                "started_at": started.isoformat(),
                "finished_at": now.isoformat(),
                "duration_ms": max(0, round((now - started).total_seconds() * 1000)),
            }]
        }

    return done


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic

    def setup_graph(self, selected_analysts=None):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst (technical analysis)
                - "social": Social media / sentiment analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
                - "policy": Policy analyst (A-stock specific)
                - "hot_money": Hot money / capital flow tracker (A-stock specific)
                - "lockup": Lockup expiry / reduction watcher (A-stock specific)
        """
        selected_analysts = list(selected_analysts or [])
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(
                self.quick_thinking_llm
            )
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(
                self.quick_thinking_llm
            )
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm
            )
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.quick_thinking_llm
            )
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        if "policy" in selected_analysts:
            analyst_nodes["policy"] = create_policy_analyst(
                self.quick_thinking_llm
            )
            tool_nodes["policy"] = self.tool_nodes["policy"]

        if "hot_money" in selected_analysts:
            analyst_nodes["hot_money"] = create_hot_money_tracker(
                self.quick_thinking_llm
            )
            tool_nodes["hot_money"] = self.tool_nodes["hot_money"]

        if "lockup" in selected_analysts:
            analyst_nodes["lockup"] = create_lockup_watcher(
                self.quick_thinking_llm
            )
            tool_nodes["lockup"] = self.tool_nodes["lockup"]

        # Create quality gate node
        quality_gate_node = create_quality_gate(self.quick_thinking_llm)

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add isolated analyst branches. Each branch retains its own messages so
        # concurrent ToolMessages can never be consumed by a different analyst.
        for analyst_type, node in analyst_nodes.items():
            analyst_name = f"{analyst_type.capitalize()} Analyst"
            tools_name = f"tools_{analyst_type}"
            done_name = f"Done {analyst_type.capitalize()}"
            message_field = _MESSAGE_FIELDS[analyst_type]
            workflow.add_node(
                analyst_name,
                timed_node(
                    analyst_name,
                    _isolated_analyst_node(node, message_field),
                    stage=analyst_type,
                ),
            )
            workflow.add_node(
                tools_name,
                timed_node(
                    tools_name,
                    _isolated_tool_node(tool_nodes[analyst_type], message_field),
                    stage=analyst_type,
                ),
            )
            workflow.add_node(
                done_name,
                timed_node(
                    done_name,
                    _analyst_done_node(analyst_type),
                    stage=analyst_type,
                ),
            )

        # Add quality gate + other nodes
        workflow.add_node("Quality Gate", timed_node("Quality Gate", quality_gate_node, stage="quality_gate", kind="stage"))
        workflow.add_node("Bull Researcher", timed_node("Bull Researcher", bull_researcher_node, stage="debate", kind="stage"))
        workflow.add_node("Bear Researcher", timed_node("Bear Researcher", bear_researcher_node, stage="debate", kind="stage"))
        workflow.add_node("Research Manager", timed_node("Research Manager", research_manager_node, stage="debate", kind="stage"))
        workflow.add_node("Trader", timed_node("Trader", trader_node, stage="trader", kind="stage"))
        workflow.add_node("Aggressive Analyst", timed_node("Aggressive Analyst", aggressive_analyst, stage="risk", kind="stage"))
        workflow.add_node("Neutral Analyst", timed_node("Neutral Analyst", neutral_analyst, stage="risk", kind="stage"))
        workflow.add_node("Conservative Analyst", timed_node("Conservative Analyst", conservative_analyst, stage="risk", kind="stage"))
        workflow.add_node("Portfolio Manager", timed_node("Portfolio Manager", portfolio_manager_node, stage="pm", kind="stage"))

        # Fan out all selected analysts from START and join only after every
        # independent branch has produced its final report.
        done_nodes = []
        for analyst_type in selected_analysts:
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_done = f"Done {analyst_type.capitalize()}"
            message_field = _MESSAGE_FIELDS[analyst_type]
            done_nodes.append(current_done)

            workflow.add_edge(START, current_analyst)

            workflow.add_conditional_edges(
                current_analyst,
                _analyst_router(message_field, current_tools, current_done),
                [current_tools, current_done],
            )
            workflow.add_edge(current_tools, current_analyst)

        workflow.add_edge(done_nodes, "Quality Gate")

        workflow.add_edge("Quality Gate", "Bull Researcher")

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Conservative Analyst": "Conservative Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Aggressive Analyst": "Aggressive Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )

        workflow.add_edge("Portfolio Manager", END)

        return workflow
