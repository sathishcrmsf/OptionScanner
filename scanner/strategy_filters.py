"""
# DEPRECATED — not imported anywhere. Logic is in options_scanner.py filter_options().
# WARNING: premium formula here uses bid only (not midpoint) — do not use.

strategy_filters.py
-------------------
Implements the core screening rules for cash‑secured put opportunities.
The module works on the DataFrame returned by ``indicators.calculate_greeks``.
"""

import pandas as pd
from typing import Tuple, List, Dict, Any

# Named DTE presets — use these as dte_min/dte_max kwargs
DTE_PRESETS: Dict[str, Tuple[int, int]] = {
    "WEEKLY":    (1,   7),
    "MONTHLY":   (21,  35),
    "STANDARD":  (38,  52),   # classic 45-DTE theta sweet spot
    "QUARTERLY": (60,  90),
    "LEAPS":     (180, 730),
}

# ----------------------------------------------------------------------
# Helper: compute risk‑adjusted yield (annualized return on cash)
# ----------------------------------------------------------------------
def _risk_adjusted_yield(row: pd.Series, cash_needed: float) -> float:
    """Return annualized yield % for a put."""
    premium = row["bid"] * 100.0
    if cash_needed <= 0:
        return 0.0
    days = row.get("days_to_exp", 365)
    years = max(days / 365.0, 0.001)
    return (premium / cash_needed) / years * 100.0


# ----------------------------------------------------------------------
# Core filter implementation
# ----------------------------------------------------------------------
def filter_opportunities(
    df: pd.DataFrame,
    underlying_price: float,
    dte_min: int = 1,
    dte_max: int = 730,
    min_open_interest: int = 100,
    min_avg_volume: int = 1_000_000,
    max_bid_ask_spread_pct: float = 0.10,
    delta_range: Tuple[float, float] = (-0.30, -0.10),
    flag_min_risk_adj_yield: float = 10.0,
    flag_min_distance_otm: float = 15.0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (regular_candidates, flagged_opportunities).

    The function adds a few derived columns to the DataFrame:
        * cash_needed – strike * 100
        * risk_adj_yield – annualised premium / cash_needed (%)
        * distance_otm – % out‑of‑the‑money relative to spot
        * flag – True if both yield and OTM distance exceed thresholds

    Parameters
    ----------
    dte_min : int
        Minimum days to expiration (inclusive). Use DTE_PRESETS for named ranges.
    dte_max : int
        Maximum days to expiration (inclusive).
    """
    # ------------------------------------------------------------------
    # 1. Basic structural filters
    # ------------------------------------------------------------------
    today = pd.Timestamp.utcnow().tz_localize(None)
    df = df.copy()
    df["expiration"] = pd.to_datetime(df["expiration"])
    df["days_to_exp"] = (df["expiration"] - today).dt.days

    # Keep only puts – scanner is put‑centric
    df = df[df["option_type"].str.lower() == "put"].copy()

    # Cash required for one contract (100 shares)
    df["cash_needed"] = df["strike"] * 100.0

    # Spread % check (skip rows with zero mid-price)
    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    df["spread_pct"] = (df["ask"] - df["bid"]).abs() / df["mid"].replace(0, float("nan"))
    df = df[df["spread_pct"].notna() & (df["spread_pct"] <= max_bid_ask_spread_pct)]

    # Open interest threshold (share volume is checked at ticker level, not per contract)
    df = df[df["open_interest"] >= min_open_interest]

    # DTE window — both min and max
    df = df[(df["days_to_exp"] >= dte_min) & (df["days_to_exp"] <= dte_max)]

    # Delta window
    low, high = delta_range
    df = df[(df["delta"] >= low) & (df["delta"] <= high)]

    # ------------------------------------------------------------------
    # 2. Derived metrics
    # ------------------------------------------------------------------
    df["risk_adj_yield"] = df.apply(lambda r: _risk_adjusted_yield(r, r["cash_needed"]), axis=1)
    df["distance_otm"] = (underlying_price - df["strike"]) / underlying_price * 100.0

    # ------------------------------------------------------------------
    # 3. Flag exceptional opportunities
    # ------------------------------------------------------------------
    flag_cond = (
        (df["risk_adj_yield"] >= flag_min_risk_adj_yield)
        & (df["distance_otm"] >= flag_min_distance_otm)
    )
    df["flag"] = flag_cond

    # Split
    candidates = df[~df["flag"]].reset_index(drop=True)
    flagged = df[df["flag"]].reset_index(drop=True)

    # Keep a tidy set of columns for downstream use
    keep = [
        "contract_symbol",
        "strike",
        "expiration",
        "days_to_exp",
        "bid",
        "ask",
        "mid",
        "open_interest",
        "volume",
        "implied_volatility",
        "delta",
        "cash_needed",
        "risk_adj_yield",
        "distance_otm",
        "flag",
    ]
    return candidates[keep], flagged[keep]


# ----------------------------------------------------------------------
# Convenience wrapper – run the whole pipeline for a list of tickers
# ----------------------------------------------------------------------
def scan_tickers(
    ticker_to_chain: Dict[str, pd.DataFrame],
    ticker_to_price: Dict[str, float],
    **filter_kwargs,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Iterate over tickers, calculate Greeks, apply filters, aggregate.

    Returns (all_candidates, flagged) – each DataFrame includes a ``ticker`` column.
    """
    from scanner import indicators  # local import to avoid circular deps

    cand_frames: List[pd.DataFrame] = []
    flagged_frames: List[pd.DataFrame] = []

    for ticker, chain in ticker_to_chain.items():
        spot = ticker_to_price.get(ticker)
        if spot is None:
            continue
        greek_df = indicators.calculate_greeks(chain, underlying_price=spot)
        c, f = filter_opportunities(greek_df, underlying_price=spot, **filter_kwargs)
        if not c.empty:
            c["ticker"] = ticker
            cand_frames.append(c)
        if not f.empty:
            f["ticker"] = ticker
            flagged_frames.append(f)

    candidates_df = pd.concat(cand_frames, ignore_index=True) if cand_frames else pd.DataFrame()
    flagged_df = pd.concat(flagged_frames, ignore_index=True) if flagged_frames else pd.DataFrame()
    return candidates_df, flagged_df


# ----------------------------------------------------------------------
# Simple CLI sanity‑check
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from scanner.yf_session import ticker as yf_ticker

    from symbol_lists import watchlist_parser
    from scanner import option_chains

    watch = watchlist_parser.load_watchlist()
    prices = {t: yf_ticker(t).info["regularMarketPrice"] for t in watch}
    chains = {t: option_chains.get_option_chain(t) for t in watch}
    cand, flagged = scan_tickers(chains, prices)
    print("=== Regular candidates ===")
    print(cand.head())
    print("\n=== Flagged (high‑yield) ===")
    print(flagged.head())
