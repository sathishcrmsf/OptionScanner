"""
scanner — core library for the cash-secured put options scanner.

Submodules
----------
indicators      Black-Scholes Greek calculations
option_chains   yfinance option chain fetcher with caching
strategy_filters  Screening rules and opportunity ranking
alpaca_config   Alpaca API credential loader
backtest        Lightweight back-testing harness
"""

from scanner.indicators import calculate_greeks
from scanner.option_chains import get_option_chain
from scanner.strategy_filters import filter_opportunities, scan_tickers
from scanner.alpaca_config import get_alpaca_credentials, AlpacaCredentials

__all__ = [
    "calculate_greeks",
    "get_option_chain",
    "filter_opportunities",
    "scan_tickers",
    "get_alpaca_credentials",
    "AlpacaCredentials",
]
