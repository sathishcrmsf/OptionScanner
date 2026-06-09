"""
option_chains.py
----------------
Utility to fetch option chain data using yfinance with simple caching.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

from scanner.yf_session import ticker as yf_ticker

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
CACHE_DIR.mkdir(exist_ok=True)

def _cache_path(ticker: str, expiry: str) -> Path:
    safe = ticker.replace('^','').replace('/','_')
    return CACHE_DIR / f"{safe}_{expiry}.json"

def _load_cache(ticker: str, expiry: str) -> Optional[pd.DataFrame]:
    p = _cache_path(ticker, expiry)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text())
        return pd.DataFrame(data)
    except Exception:
        return None

def _save_cache(ticker: str, expiry: str, df: pd.DataFrame) -> None:
    p = _cache_path(ticker, expiry)
    p.write_text(df.to_json(orient="records"))

def get_option_chain(
    ticker: str,
    expiry: Optional[str] = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Fetch option chain for *ticker*.
    If *expiry* is None the nearest expiry offered by yfinance is used.
    Returns a DataFrame with both calls and puts, unified under columns:
    contract_symbol, strike, expiration, last_price, bid, ask, volume,
    open_interest, implied_volatility, delta (if provided), option_type.
    """
    yf_ticker_obj = yf_ticker(ticker)
    if expiry is None:
        expiries = yf_ticker_obj.options
        if not expiries:
            raise ValueError(f"No expiries found for {ticker}")
        expiry = expiries[0]
    if use_cache:
        cached = _load_cache(ticker, expiry)
        if cached is not None:
            return cached

    # fetch chain using yfinance
    chain = yf_ticker_obj.option_chain(expiry)
    calls = chain.calls.copy()
    puts = chain.puts.copy()
    calls["option_type"] = "call"
    puts["option_type"] = "put"
    df = pd.concat([calls, puts], ignore_index=True)
    df.rename(columns={
        "contractSymbol": "contract_symbol",
        "lastPrice": "last_price",
        "openInterest": "open_interest",
        "impliedVolatility": "implied_volatility",
    }, inplace=True)
    df["expiration"] = pd.to_datetime(expiry)
    # Ensure required columns exist
    for col in ["delta", "implied_volatility", "bid", "ask"]:
        if col not in df.columns:
            df[col] = None
    if use_cache:
        _save_cache(ticker, expiry, df)
    return df

if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv)>1 else "AAPL"
    print(get_option_chain(t).head())
