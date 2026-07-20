from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.dataflows.config import get_config

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get config from layered defaults (config.yaml + env + default_config.py)
config = get_config()
config["deep_think_llm"] = "gpt-5.4-mini"
config["quick_think_llm"] = "gpt-5.4-mini"
config["max_debate_rounds"] = 1

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
