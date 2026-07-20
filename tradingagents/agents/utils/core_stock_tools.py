from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_stock_data(
    symbol: Annotated[str, "6-digit A-stock code (e.g. 600379). Must be numeric, NOT company name or Chinese text"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    indicators: Annotated[str, "Optional: compute technical indicators together with price data. "
        "Use 'all' for common indicators (close_10_ema, close_50_sma, macd, "
        "macds, macdh, rsi, boll, boll_ub, boll_lb, vwma), or a comma-separated "
        "list: close_50_sma, close_200_sma, close_10_ema, macd, macds, macdh, "
        "rsi, boll, boll_ub, boll_lb, atr, vwma, mfi"] = "",
) -> str:
    """
    Retrieve stock price data (OHLCV) for a given stock code, with optional technical indicators.
    When indicators='all' or a comma-separated list is provided, the output includes
    both the OHLCV CSV and a technical indicators section (latest values + recent trend).
    This avoids separate get_indicators calls.
    Args:
        symbol (str): 6-digit A-stock code.
        start_date (str): Start date in yyyy-mm-dd format.
        end_date (str): End date in yyyy-mm-dd format.
        indicators (str): Optional. 'all' for common indicators, or comma-separated list.
    Returns:
        str: OHLCV data with optional technical indicators.
    """
    return route_to_vendor("get_stock_data", symbol, start_date, end_date, indicators)
