# TradingAgents/graph/trading_graph.py

import logging
import os
from pathlib import Path
import json
from datetime import datetime, timedelta
import time
from typing import Dict, Any, Tuple, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

from tradingagents.llm_clients import create_llm_client

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.agents.quality_ledger import RunToolCache, create_tracked_tool_node
from tradingagents.dataflows.config import set_config

# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news,
    get_profit_forecast,
    get_hot_stocks,
    get_northbound_flow,
    get_concept_blocks,
    get_fund_flow,
    get_dragon_tiger_board,
    get_lockup_expiry,
    get_industry_comparison,
)

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor
from .performance import (
    ModelTimingCallback,
    make_timing_entry,
    summarize_performance_ledger,
)


FULL_ANALYSTS = [
    "market", "social", "news", "fundamentals", "policy", "hot_money", "lockup",
]
FAST_ANALYSTS = ["market", "news", "fundamentals"]


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=None,
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = (config or DEFAULT_CONFIG).copy()
        self.callbacks = callbacks or []
        self.analysis_mode = str(self.config.get("analysis_mode", "full")).lower()
        if self.analysis_mode not in {"full", "fast"}:
            raise ValueError("analysis_mode must be 'full' or 'fast'")
        if selected_analysts is None:
            selected_analysts = (
                FAST_ANALYSTS if self.analysis_mode == "fast" else FULL_ANALYSTS
            )
        self.selected_analysts = list(selected_analysts)

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        # Initialize LLMs with provider-specific thinking configuration
        llm_kwargs = self._get_provider_kwargs()

        # Add callbacks to kwargs if provided (passed to LLM constructor)
        self.model_timing = ModelTimingCallback()
        llm_callbacks = [*self.callbacks, self.model_timing]
        llm_kwargs["callbacks"] = llm_callbacks

        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()
        
        self.memory_log = TradingMemoryLog(self.config)

        # One cache exists only for this graph/run. It is cleared at prepare time
        # and never crosses analyses, so realtime data cannot leak into another run.
        self.tool_cache = RunToolCache()

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(self.selected_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, Any]:
        """Create tracked tool nodes for different data sources."""
        return {
            "market": create_tracked_tool_node("market",
                [
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                ], self.tool_cache
            ),
            "social": create_tracked_tool_node("social",
                [
                    # News tools for social media analysis
                    get_news,
                ], self.tool_cache
            ),
            "news": create_tracked_tool_node("news",
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ], self.tool_cache
            ),
            "fundamentals": create_tracked_tool_node("fundamentals",
                [
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                    get_profit_forecast,
                    get_industry_comparison,
                ], self.tool_cache
            ),
            "policy": create_tracked_tool_node("policy",
                [
                    get_news,
                    get_global_news,
                ], self.tool_cache
            ),
            "hot_money": create_tracked_tool_node("hot_money",
                [
                    get_stock_data,
                    get_news,
                    get_insider_transactions,
                    get_hot_stocks,
                    get_northbound_flow,
                    get_concept_blocks,
                    get_fund_flow,
                    get_dragon_tiger_board,
                    get_industry_comparison,
                ], self.tool_cache
            ),
            "lockup": create_tracked_tool_node("lockup",
                [
                    get_insider_transactions,
                    get_news,
                    get_fundamentals,
                    get_lockup_expiry,
                ], self.tool_cache
            ),
        }

    @staticmethod
    def _detect_exchange(ticker: str) -> Optional[str]:
        """Detect A-stock exchange from 6-digit ticker prefix.

        Returns ``"sh"`` (Shanghai), ``"sz"`` (Shenzhen), or ``None`` if the
        ticker doesn't match the 6-digit A-stock code convention.
        """
        if not ticker.isdigit() or len(ticker) != 6:
            return None
        code = int(ticker)
        # Shanghai: 600–609, 601–609, 603–609, 605–609, 688–689
        if code // 1000 in (600, 601, 603, 605, 688):
            return "sh"
        # Shenzhen: 000–004, 001–004, 002–004, 003–004, 300–301, 301–302
        if code // 1000 in (0, 1, 2, 3, 300, 301):
            return "sz"
        return None

    def _resolve_benchmark(self, ticker: str) -> str:
        """Pick the benchmark ticker for alpha calculation against ``ticker``.

        Resolution order:
        1. ``config["benchmark_ticker"]`` — explicit override for all tickers
        2. yfinance-style exchange suffix match (``.SS``, ``.SZ``)
        3. 6-digit A-stock code prefix → exchange key → benchmark_map
        4. ``benchmark_map[""]`` fallback (CSI 300 by default)
        """
        explicit = self.config.get("benchmark_ticker")
        if explicit:
            return explicit
        benchmark_map = self.config.get("benchmark_map", {})
        ticker_upper = ticker.upper()
        # yfinance suffix match first
        for suffix, benchmark in benchmark_map.items():
            if suffix.startswith(".") and ticker_upper.endswith(suffix.upper()):
                return benchmark
        # 6-digit A-stock code → exchange key
        exchange = TradingAgentsGraph._detect_exchange(ticker)
        if exchange and exchange in benchmark_map:
            return benchmark_map[exchange]
        return benchmark_map.get("", "000300.SS")

    def _fetch_returns(
        self, ticker: str, trade_date: str, holding_days: int = 5,
        benchmark: str = "000300.SS",
    ) -> Tuple[Optional[float], Optional[float], Optional[int]]:
        """Fetch raw and alpha return for ticker over holding_days from trade_date.

        ``benchmark`` is the index used as the alpha baseline (resolved by the
        caller via ``_resolve_benchmark``). Returns ``(raw_return, alpha_return,
        actual_holding_days)`` or ``(None, None, None)`` if price data is
        unavailable (too recent, delisted, or network error).
        """
        try:
            start = datetime.strptime(trade_date, "%Y-%m-%d")
            end = start + timedelta(days=holding_days + 7)  # buffer for weekends/holidays
            end_str = end.strftime("%Y-%m-%d")

            stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
            bench = yf.Ticker(benchmark).history(start=trade_date, end=end_str)

            if len(stock) < 2 or len(bench) < 2:
                return None, None, None

            actual_days = min(holding_days, len(stock) - 1, len(bench) - 1)
            raw = float(
                (stock["Close"].iloc[actual_days] - stock["Close"].iloc[0])
                / stock["Close"].iloc[0]
            )
            bench_ret = float(
                (bench["Close"].iloc[actual_days] - bench["Close"].iloc[0])
                / bench["Close"].iloc[0]
            )
            alpha = raw - bench_ret
            return raw, alpha, actual_days
        except Exception as e:
            logger.warning(
                "Could not resolve outcome for %s on %s vs %s (will retry next run): %s",
                ticker, trade_date, benchmark, e,
            )
            return None, None, None

    def _resolve_pending_entries(self, ticker: str) -> None:
        """Resolve pending log entries for ticker at the start of a new run.

        Fetches returns for each same-ticker pending entry, generates reflections,
        then writes all updates in a single atomic batch write to avoid redundant I/O.
        Skips entries whose price data is not yet available (too recent or delisted).

        Trade-off: only same-ticker entries are resolved per run.  Entries for
        other tickers accumulate until that ticker is run again.
        """
        pending = [e for e in self.memory_log.get_pending_entries() if e["ticker"] == ticker]
        if not pending:
            return

        benchmark = self._resolve_benchmark(ticker)
        # Human-readable label for the reflection prompt
        benchmark_label = {
            "000001.SS": "SSE Composite (上证综指)",
            "399001.SZ": "SZSE Component (深证成指)",
            "000300.SS": "CSI 300 (沪深300)",
        }.get(benchmark, benchmark)

        updates = []
        for entry in pending:
            raw, alpha, days = self._fetch_returns(
                ticker, entry["date"], benchmark=benchmark,
            )
            if raw is None:
                continue  # price not available yet — try again next run
            reflection = self.reflector.reflect_on_final_decision(
                final_decision=entry.get("decision", ""),
                raw_return=raw,
                alpha_return=alpha,
                benchmark_name=benchmark_label,
            )
            updates.append({
                "ticker": ticker,
                "trade_date": entry["date"],
                "raw_return": raw,
                "alpha_return": alpha,
                "holding_days": days,
                "reflection": reflection,
            })

        if updates:
            self.memory_log.batch_update_with_outcomes(updates)

    def propagate(self, company_name, trade_date):
        """Run the trading agents graph for a company on a specific date.

        When ``checkpoint_enabled`` is set in config, the graph is recompiled
        with a per-ticker SqliteSaver so a crashed run can resume from the last
        successful node on a subsequent invocation with the same ticker+date.
        """
        return self._run_graph(company_name, trade_date)

    def prepare_graph_run(
        self,
        company_name,
        trade_date,
        callbacks: Optional[List] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], Optional[int]]:
        """Prepare graph input/args for a fresh or resumed run.

        Returns ``(initial_state, args, checkpoint_step)``. When a checkpoint
        already exists, ``initial_state`` is ``None`` so LangGraph resumes the
        existing thread instead of replaying completed nodes.
        """
        self.ticker = company_name

        # Resolve any pending memory-log entries for this ticker before the pipeline runs.
        self._resolve_pending_entries(company_name)

        # Start a clean run-local measurement/cache segment after reflection work.
        if hasattr(self, "tool_cache"):
            self.tool_cache.clear()
        if hasattr(self, "model_timing"):
            self.model_timing.reset()
        self._run_started_at = datetime.now().astimezone().isoformat()
        self._run_started_perf = time.perf_counter()

        checkpoint_enabled = self.config.get("checkpoint_enabled")
        resume_step = None

        # Recompile with a checkpointer if the user opted in.
        if checkpoint_enabled:
            self._checkpointer_ctx = get_checkpointer(
                self.config["data_cache_dir"], company_name
            )
            saver = self._checkpointer_ctx.__enter__()
            self.graph = self.workflow.compile(checkpointer=saver)

            resume_step = checkpoint_step(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )
            if resume_step is not None:
                logger.info(
                    "Resuming from step %d for %s on %s",
                    resume_step,
                    company_name,
                    trade_date,
                )
            else:
                logger.info("Starting fresh for %s on %s", company_name, trade_date)

        args = self.propagator.get_graph_args(callbacks=callbacks)

        # Inject thread_id so same ticker+date resumes, different date starts fresh.
        if checkpoint_enabled:
            tid = thread_id(company_name, str(trade_date))
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        if checkpoint_enabled and resume_step is not None:
            return None, args, resume_step

        # Initialize state only for fresh runs. Passing a new initial state to
        # LangGraph would start a new run and replay completed nodes.
        past_context = self.memory_log.get_past_context(company_name)
        init_agent_state = self.propagator.create_initial_state(
            company_name,
            trade_date,
            past_context=past_context,
            analysis_mode=getattr(self, "analysis_mode", "full"),
            selected_analysts=getattr(self, "selected_analysts", FULL_ANALYSTS),
        )
        return init_agent_state, args, resume_step

    def finalize_graph_run(self, company_name, trade_date, final_state):
        """Persist a completed run and clear its checkpoint."""
        performance_ledger = final_state.setdefault("performance_ledger", [])
        if hasattr(self, "model_timing"):
            performance_ledger.extend(self.model_timing.snapshot())
        if hasattr(self, "_run_started_perf"):
            performance_ledger.append(make_timing_entry(
                kind="run",
                name="graph_execution",
                status="success",
                started_at=self._run_started_at,
                duration_ms=max(
                    0,
                    round((time.perf_counter() - self._run_started_perf) * 1000),
                ),
                stage="pipeline",
            ))

        self._apply_data_quality_limit(final_state)
        self.curr_state = final_state

        # Store decision for deferred reflection on the next same-ticker run.
        # Never let an unsupported BUY/SELL recommendation from an incomplete
        # run become “past experience” for a later analysis.
        decision_for_memory = final_state["final_trade_decision"]
        if final_state.get("data_quality_status") == "低":
            decision_for_memory = "关键数据未完整返回，本次未形成可执行结论。"
        memory_started_at = datetime.now().astimezone().isoformat()
        memory_started = time.perf_counter()
        self.memory_log.store_decision(
            ticker=company_name,
            trade_date=trade_date,
            final_trade_decision=decision_for_memory,
        )
        performance_ledger.append(make_timing_entry(
            kind="persistence",
            name="memory_log",
            status="success",
            started_at=memory_started_at,
            duration_ms=round((time.perf_counter() - memory_started) * 1000),
            stage="persistence",
        ))

        # Clear checkpoint on successful completion to avoid stale state.
        if self.config.get("checkpoint_enabled"):
            checkpoint_started_at = datetime.now().astimezone().isoformat()
            checkpoint_started = time.perf_counter()
            clear_checkpoint(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )
            performance_ledger.append(make_timing_entry(
                kind="persistence",
                name="checkpoint_cleanup",
                status="success",
                started_at=checkpoint_started_at,
                duration_ms=round((time.perf_counter() - checkpoint_started) * 1000),
                stage="persistence",
            ))

        # Persist once to measure real JSON serialization/write time, then append
        # that sanitized duration and rewrite the final auditable payload.
        final_state["performance_summary"] = summarize_performance_ledger(
            performance_ledger
        )
        log_started_at = datetime.now().astimezone().isoformat()
        log_started = time.perf_counter()
        self._log_state(trade_date, final_state)
        performance_ledger.append(make_timing_entry(
            kind="persistence",
            name="result_json",
            status="success",
            started_at=log_started_at,
            duration_ms=round((time.perf_counter() - log_started) * 1000),
            stage="persistence",
        ))
        final_state["performance_summary"] = summarize_performance_ledger(
            performance_ledger
        )
        self._log_state(trade_date, final_state)

        # A critical data failure is not an investment rating. Do not let a
        # BUY/SELL word retained in the internal audit text become a user-facing
        # instruction merely because the signal parser sees it.
        if final_state.get("data_quality_status") == "低":
            return "DataIncomplete"
        return self.process_signal(final_state["final_trade_decision"])

    @staticmethod
    def _apply_data_quality_limit(final_state) -> None:
        """在基础数据失败或多个主要领域不可用时限制最终结论。"""
        if final_state.get("data_quality_status") != "低":
            return
        notice = "⚠️ 数据不全：关键数据没有取到。本次分析只能作参考，不要据此直接买卖。"
        decision = str(final_state.get("final_trade_decision", "")).strip()
        if not decision.startswith(notice):
            final_state["final_trade_decision"] = (
                f"{notice}\n\n{decision}" if decision else notice
            )

    def close_graph_run(self) -> None:
        """Close the active checkpointer context, if any."""
        if self._checkpointer_ctx is not None:
            self._checkpointer_ctx.__exit__(None, None, None)
            self._checkpointer_ctx = None
            self.graph = self.workflow.compile()

    def _run_graph(self, company_name, trade_date):
        """Execute the graph and write the resulting state to disk and memory log."""
        init_agent_state, args, _ = self.prepare_graph_run(company_name, trade_date)

        try:
            if self.debug:
                trace = []
                for chunk in self.graph.stream(init_agent_state, **args):
                    if len(chunk["messages"]) == 0:
                        pass
                    else:
                        chunk["messages"][-1].pretty_print()
                        trace.append(chunk)
                final_state = trace[-1]
            else:
                final_state = self.graph.invoke(init_agent_state, **args)

            signal = self.finalize_graph_run(company_name, trade_date, final_state)
            return final_state, signal
        finally:
            self.close_graph_run()

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "analysis_mode": final_state.get("analysis_mode", "full"),
            "selected_analysts": final_state.get("selected_analysts", FULL_ANALYSTS),
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "policy_report": final_state.get("policy_report", ""),
            "hot_money_report": final_state.get("hot_money_report", ""),
            "lockup_report": final_state.get("lockup_report", ""),
            "data_quality_summary": final_state.get("data_quality_summary", ""),
            "data_quality_status": final_state.get("data_quality_status", ""),
            "data_quality_constraints": final_state.get(
                "data_quality_constraints", ""
            ),
            "tool_execution_ledger": final_state.get("tool_execution_ledger", []),
            "performance_ledger": final_state.get("performance_ledger", []),
            "performance_summary": final_state.get("performance_summary", {}),
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # Save to file. Reject ticker values that would escape the
        # results directory when joined as a path component.
        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)
