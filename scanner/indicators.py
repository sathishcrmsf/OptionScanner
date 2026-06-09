"""
indicators.py
-------------
Calculate option Greeks (Delta, Gamma, Vega, Theta, Rho) using the
Black‑Scholes model. The functions accept a pandas DataFrame that
contains the columns produced by ``option_chains.get_option_chain``:

    contract_symbol, strike, expiration, last_price, bid, ask,
    volume, open_interest, implied_volatility, delta (optional)

The calculator derives the missing Greeks and returns a DataFrame with
the added columns.
"""

import math
from datetime import datetime, timezone
from typing import Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm

from typing import Optional as _Optional
_cached_risk_free_rate: _Optional[float] = None

def fetch_risk_free_rate() -> float:
    """Fetch the current 13-week T-bill rate from ^IRX. Falls back to 5.25% if unavailable."""
    global _cached_risk_free_rate
    if _cached_risk_free_rate is not None:
        return _cached_risk_free_rate
    try:
        from scanner.yf_session import ticker as yf_ticker
        irx = yf_ticker("^IRX").info.get("regularMarketPrice")
        if irx and irx > 0:
            _cached_risk_free_rate = irx / 100.0
            return _cached_risk_free_rate
    except Exception:
        pass
    _cached_risk_free_rate = 0.0525
    return _cached_risk_free_rate


def reset_risk_free_rate_cache() -> None:
    global _cached_risk_free_rate
    _cached_risk_free_rate = None

# ----------------------------------------------------------------------
# Helper: convert a price/volatility to the Black‑Scholes d1/d2 terms
# ----------------------------------------------------------------------
def _d1_d2(
    S: float,    # underlying spot price
    K: float,    # strike
    T: float,    # time to expiry in years
    r: float,    # risk‑free rate (annual)
    sigma: float # implied vol (annual)
) -> Tuple[float, float]:
    """Return d1, d2 for Black‑Scholes."""
    if T <= 0 or sigma <= 0:
        # Edge cases – avoid divide‑by‑zero
        return 0.0, 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


# ----------------------------------------------------------------------
# Core Greek calculators (call & put)
# ----------------------------------------------------------------------
def _greeks_call(
    S: float, K: float, T: float, r: float, sigma: float
) -> Tuple[float, float, float, float, float]:
    """Return (delta, gamma, vega, theta, rho) for a *call*."""
    d1, d2 = _d1_d2(S, K, T, r, sigma)

    delta = norm.cdf(d1)
    gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
    vega = S * norm.pdf(d1) * math.sqrt(T) / 100.0        # per 1% vol change
    theta = (
        -S * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
        - r * K * math.exp(-r * T) * norm.cdf(d2)
    ) / 365.0                                              # per day
    rho = K * T * math.exp(-r * T) * norm.cdf(d2) / 100.0   # per 1% rate change
    return delta, gamma, vega, theta, rho


def _greeks_put(
    S: float, K: float, T: float, r: float, sigma: float
) -> Tuple[float, float, float, float, float]:
    """Return (delta, gamma, vega, theta, rho) for a *put*."""
    d1, d2 = _d1_d2(S, K, T, r, sigma)

    delta = norm.cdf(d1) - 1
    gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
    vega = S * norm.pdf(d1) * math.sqrt(T) / 100.0
    theta = (
        -S * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
        + r * K * math.exp(-r * T) * norm.cdf(-d2)
    ) / 365.0
    rho = -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100.0
    return delta, gamma, vega, theta, rho


# ----------------------------------------------------------------------
# Public API – apply Greeks to a DataFrame
# ----------------------------------------------------------------------
def calculate_greeks(
    df: pd.DataFrame,
    underlying_price: float,
    risk_free_rate: float = None,
    today: datetime = None,
) -> pd.DataFrame:
    """
    Add Black‑Scholes Greeks to an option‑chain DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain the columns:
        ``strike, expiration, implied_volatility, option_type``.
        ``option_type`` values must be exactly ``"call"`` or ``"put"``.
    underlying_price : float
        Current spot price of the underlying equity.
    risk_free_rate : float, optional
        Annual risk‑free rate (default = 2.54%).
    today : datetime, optional
        Date used for ``T`` calculation; defaults to ``datetime.utcnow()``.

    Returns
    -------
    pd.DataFrame
        The original frame plus the columns:
        ``delta, gamma, vega, theta, rho``.
    """
    if risk_free_rate is None:
        risk_free_rate = fetch_risk_free_rate()
    if today is None:
        today = datetime.utcnow()

    # Ensure required columns exist
    required = {"strike", "expiration", "implied_volatility", "option_type"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns for Greek calculation: {missing}")

    out = df.copy()
    out["delta"] = np.nan
    out["gamma"] = np.nan
    out["vega"] = np.nan
    out["theta"] = np.nan
    out["rho"] = np.nan

    for idx, row in out.iterrows():
        K = float(row["strike"])
        expiry = pd.to_datetime(row["expiration"])
        T = max((expiry - today).days / 365.0, 0.0)   # years to expiry
        sigma = float(row["implied_volatility"])
        if sigma == 0 or T == 0:
            continue
        if row["option_type"].lower() == "call":
            delta, gamma, vega, theta, rho = _greeks_call(
                underlying_price, K, T, risk_free_rate, sigma
            )
        else:
            delta, gamma, vega, theta, rho = _greeks_put(
                underlying_price, K, T, risk_free_rate, sigma
            )
        out.at[idx, "delta"] = delta
        out.at[idx, "gamma"] = gamma
        out.at[idx, "vega"] = vega
        out.at[idx, "theta"] = theta
        out.at[idx, "rho"] = rho

    return out


# ----------------------------------------------------------------------
# Simple CLI sanity‑check
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from scanner import option_chains
    from scanner.yf_session import ticker as yf_ticker

    ticker = "AAPL"
    chain = option_chains.get_option_chain(ticker)
    spot = yf_ticker(ticker).info["regularMarketPrice"]
    greek_df = calculate_greeks(chain, underlying_price=spot)
    print(greek_df.head())
