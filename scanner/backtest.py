"""
backtest.py
-----------
A lightweight back‑testing harness that runs the scanner over historic
option data and records performance metrics.

The harness assumes you have already downloaded historic option‑chain CSVs
for each underlying (e.g., via yfinance’s ``download`` with the ``period``
parameter). The CSVs should live under ``historical_data/<ticker>_<date>.csv``
and contain the same columns produced by ``option_chains.get_option_chain``.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from scanner import indicators, strategy_filters


# ----------------------------------------------------------------------
# Load a historic chain CSV for a given ticker & date
# ----------------------------------------------------------------------
def load_historic_chain(ticker: str, date: str) -> pd.DataFrame:
    """Load a historic option chain.

    Parameters
    ----------
    ticker : str
        Underlying ticker symbol.
    date : str
        Date string ``YYYY-MM-DD``; the file is expected at
        ``historical_data/<ticker>_<date>.csv``.
    """
    path = Path("historical_data") / f"{ticker}_{date}.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Missing historic chain: {path}")
    return pd.read_csv(path)


# ----------------------------------------------------------------------
# Run a single day back‑test for a ticker/date
# ----------------------------------------------------------------------
def run_day(
    ticker: str,
    date: str,
    spot_price: float,
    **filter_kwargs,
) -> Tuple[int, int]:
    """Return (num_candidates, num_flagged) for a given day.

    The function loads the historic chain, calculates Greeks, applies the
    screening filters and returns the counts of normal candidates and the
    flagged (high‑yield) ones.
    """
    chain = load_historic_chain(ticker, date)
    greek_df = indicators.calculate_greeks(chain, underlying_price=spot_price)
    cand, flagged = strategy_filters.filter_opportunities(
        greek_df,
        underlying_price=spot_price,
        **filter_kwargs,
    )
    return len(cand), len(flagged)


# ----------------------------------------------------------------------
# Orchestrate a multi‑day back‑test across many tickers
# ----------------------------------------------------------------------
def backtest(
    ticker_dates: Dict[str, List[Tuple[str, float]]],
    **filter_kwargs,
) -> Dict[str, Dict[str, int]]:
    """Run the scanner over historic data.

    ``ticker_dates`` maps a ticker to a list of ``(date, spot_price)`` tuples.
    The return value is a dict like:
    {
        "AAPL": {"candidates": 123, "flagged": 7},
        "MSFT": {"candidates": 58,  "flagged": 2},
    }
    """
    results: Dict[str, Dict[str, int]] = {}
    for ticker, date_price_list in ticker_dates.items():
        cand_total = 0
        flagged_total = 0
        for date_str, spot in date_price_list:
            try:
                c, f = run_day(ticker, date_str, spot, **filter_kwargs)
                cand_total += c
                flagged_total += f
            except FileNotFoundError:
                # Missing historic file – skip silently
                continue
        results[ticker] = {"candidates": cand_total, "flagged": flagged_total}
    return results


# ----------------------------------------------------------------------
# Simple CLI driver for ad‑hoc testing
# ----------------------------------------------------------------------
if __name__ == "__main__":
    INPUT_FILE = "backtest_input.json"
    if not os.path.exists(INPUT_FILE):
        print(f"Create a JSON file named {INPUT_FILE} with ticker→date/price mapping.")
        exit(1)

    with open(INPUT_FILE) as f:
        ticker_dates = json.load(f)  # expected format {"AAPL": [["2024-06-01", 181.2], ...]}

    # Default filter parameters – tweak as needed
    kwargs = {
        "min_days_to_expiration": 365,
        "min_open_interest": 100,
        "min_avg_volume": 1_000_000,
        "max_bid_ask_spread_pct": 0.10,
        "delta_range": (-0.30, -0.10),
        "flag_min_risk_adj_yield": 10.0,
        "flag_min_distance_otm": 15.0,
    }

    results = backtest(ticker_dates, **kwargs)
    for ticker, stats in results.items():
        print(f"{ticker}: {stats['candidates']} candidates, {stats['flagged']} flagged")