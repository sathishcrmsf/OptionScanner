"""
data_providers.py
-----------------
Multi-provider market data layer for the CSP Scanner.

Provider hierarchy
==================
1. **Alpaca**   — stock prices, OHLCV history, AND options chains
                  (same free API keys from app.alpaca.markets)
2. **yfinance** — fallback for anything Alpaca can't cover

No Tradier account needed. No SSN. Just your existing Alpaca keys.

Credentials
===========
Loaded from (in order):
  1. data/credentials.json  (git-ignored, set via Settings modal)
  2. Environment variables:  ALPACA_KEY  ALPACA_SECRET

data/credentials.json format:
  {
    "alpaca_key":    "PKxxxxxxxxxxxxxxxx",
    "alpaca_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_CREDS_FILE = Path(__file__).parent.parent / "data" / "credentials.json"


# ── Credentials ───────────────────────────────────────────────────────────────

def _load_credentials() -> Dict[str, Any]:
    creds: Dict[str, Any] = {}
    if _CREDS_FILE.exists():
        try:
            creds = json.loads(_CREDS_FILE.read_text())
            creds.pop("_comment", None)
        except Exception:
            pass
    return creds


def get_alpaca_config() -> Dict[str, str]:
    """Return {'key': ..., 'secret': ...} or {} if not configured."""
    creds = _load_credentials()
    key    = os.getenv("ALPACA_KEY")    or creds.get("alpaca_key", "")
    secret = os.getenv("ALPACA_SECRET") or creds.get("alpaca_secret", "")
    if key and secret:
        return {"key": key, "secret": secret}
    return {}


def is_alpaca_configured() -> bool:
    return bool(get_alpaca_config())


# Keep Tradier stubs so existing imports don't break (returns not-configured)
def get_tradier_config() -> Dict[str, str]:
    return {}


def is_tradier_configured() -> bool:
    return False


# ── Alpaca data client ────────────────────────────────────────────────────────

_alpaca_equity_client  = None
_alpaca_options_client = None


def _get_equity_client():
    global _alpaca_equity_client
    if _alpaca_equity_client is None:
        cfg = get_alpaca_config()
        if cfg:
            try:
                from alpaca.data import StockHistoricalDataClient
                _alpaca_equity_client = StockHistoricalDataClient(
                    api_key=cfg["key"], secret_key=cfg["secret"]
                )
                logger.info("Alpaca equity data client initialised")
            except Exception as exc:
                logger.warning("Alpaca equity client failed: %s", exc)
    return _alpaca_equity_client


def _get_options_client():
    global _alpaca_options_client
    if _alpaca_options_client is None:
        cfg = get_alpaca_config()
        if cfg:
            try:
                from alpaca.data import OptionHistoricalDataClient
                _alpaca_options_client = OptionHistoricalDataClient(
                    api_key=cfg["key"], secret_key=cfg["secret"]
                )
                logger.info("Alpaca options data client initialised")
            except Exception as exc:
                logger.warning("Alpaca options client failed: %s", exc)
    return _alpaca_options_client


# Keep old accessor for compatibility
def get_alpaca_data():
    return _get_equity_client()


# ── Stock price + volume ──────────────────────────────────────────────────────

def get_stock_price_and_volume(symbol: str) -> Optional[Dict]:
    """
    Return {'current_price': float, 'average_volume': int, 'currency': str}.
    Tries: Alpaca latest trade → Alpaca bars → yfinance history.
    """
    # 1. Alpaca latest trade (fastest)
    client = _get_equity_client()
    if client:
        try:
            from alpaca.data.requests import StockLatestTradeRequest
            req  = StockLatestTradeRequest(symbol_or_symbols=symbol)
            resp = client.get_stock_latest_trade(req)
            trade = resp.get(symbol)
            if trade and trade.price:
                price = float(trade.price)
                vol   = _alpaca_avg_volume(client, symbol)
                logger.debug("price for %s via Alpaca trade: %.2f", symbol, price)
                return {"current_price": price, "average_volume": vol, "currency": "USD"}
        except Exception as exc:
            logger.debug("Alpaca latest trade failed for %s: %s", symbol, exc)

    # 2. Alpaca bars fallback
    if client:
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            start = datetime.datetime.utcnow() - datetime.timedelta(days=5)
            req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start)
            bars = client.get_stock_bars(req)
            df = bars.df
            if df is not None and not df.empty:
                if isinstance(df.index, pd.MultiIndex):
                    df = df.xs(symbol, level="symbol")
                price = float(df["close"].iloc[-1])
                vol   = _alpaca_avg_volume(client, symbol)
                return {"current_price": price, "average_volume": vol, "currency": "USD"}
        except Exception as exc:
            logger.debug("Alpaca bars fallback failed for %s: %s", symbol, exc)

    # 3. yfinance history (chart endpoint — less throttled than .info)
    try:
        from scanner.yf_session import ticker as yf_ticker
        hist = yf_ticker(symbol).history(period="30d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
            vol   = int(hist["Volume"].mean())
            logger.debug("price for %s via yfinance fallback: %.2f", symbol, price)
            return {"current_price": price, "average_volume": vol, "currency": "USD"}
    except Exception as exc:
        logger.warning("yfinance price fallback for %s: %s", symbol, exc)

    return None


def _alpaca_avg_volume(client, symbol: str) -> int:
    """Return 30-day average daily volume via Alpaca bars."""
    try:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        start = datetime.datetime.utcnow() - datetime.timedelta(days=35)
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start)
        bars = client.get_stock_bars(req)
        df = bars.df
        if df is None or df.empty:
            return 0
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")
        return int(df["volume"].mean())
    except Exception:
        return 0


# ── OHLCV history (for pivot points + Bollinger Bands) ───────────────────────

def get_ohlcv_history(symbol: str, days: int = 65) -> Optional[pd.DataFrame]:
    """
    Return daily OHLCV DataFrame (columns: Open High Low Close Volume).
    Tries: Alpaca bars → yfinance.
    """
    # 1. Alpaca
    client = _get_equity_client()
    if client:
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            start = datetime.datetime.utcnow() - datetime.timedelta(days=days + 5)
            req = StockBarsRequest(
                symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start
            )
            bars = client.get_stock_bars(req)
            df = bars.df
            if df is not None and not df.empty:
                if isinstance(df.index, pd.MultiIndex):
                    df = df.xs(symbol, level="symbol")
                df.index = pd.to_datetime(df.index).tz_localize(None)
                df.index.name = "Date"
                df = df.rename(columns={
                    "open": "Open", "high": "High",
                    "low": "Low",   "close": "Close", "volume": "Volume",
                })
                cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]
                df = df[cols]
                if len(df) >= 21:
                    logger.debug("history for %s via Alpaca (%d bars)", symbol, len(df))
                    return df
        except Exception as exc:
            logger.debug("Alpaca history failed for %s: %s", symbol, exc)

    # 2. yfinance
    try:
        from scanner.yf_session import ticker as yf_ticker
        hist = yf_ticker(symbol).history(period=f"{days}d", interval="1d")
        if not hist.empty and len(hist) >= 21:
            logger.debug("history for %s via yfinance fallback (%d bars)", symbol, len(hist))
            return hist[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as exc:
        logger.warning("yfinance history fallback for %s: %s", symbol, exc)

    return None


# ── Options chains ────────────────────────────────────────────────────────────

def get_option_expirations(symbol: str) -> List[str]:
    """
    Return list of available expiration dates (YYYY-MM-DD).
    Tries: Alpaca option chain snapshot → yfinance.
    """
    client = _get_options_client()
    if client:
        try:
            from alpaca.data import OptionChainRequest
            # Fetch a wide window to get all expirations, then extract unique dates
            req = OptionChainRequest(
                underlying_symbol=symbol,
                expiration_date_gte=datetime.date.today(),
                expiration_date_lte=datetime.date.today() + datetime.timedelta(days=730),
                type="put",
            )
            chain = client.get_option_chain(req)
            if chain:
                exps = sorted(set(
                    snap.symbol[len(symbol):len(symbol)+6]  # YYMMDD from OCC symbol
                    for snap in chain.values()
                    if hasattr(snap, 'symbol') and len(snap.symbol) > len(symbol) + 6
                ))
                # Convert YYMMDD → YYYY-MM-DD
                result = []
                for e in exps:
                    try:
                        d = datetime.datetime.strptime(e, "%y%m%d").date()
                        result.append(d.strftime("%Y-%m-%d"))
                    except Exception:
                        pass
                if result:
                    logger.debug("expirations for %s via Alpaca: %d dates", symbol, len(result))
                    return result
        except Exception as exc:
            logger.debug("Alpaca expirations failed for %s: %s", symbol, exc)

    # yfinance fallback
    try:
        from scanner.yf_session import ticker as yf_ticker
        from options_scanner import with_retry
        return list(with_retry(lambda: yf_ticker(symbol).options) or [])
    except Exception:
        return []


def get_puts_chain(symbol: str, expirations: List[str]) -> Optional[pd.DataFrame]:
    """
    Return PUT option chain for all listed expirations as one DataFrame.
    Tries: Alpaca option snapshots → yfinance.

    Output columns (normalised):
      strike, bid, ask, delta, theta, impliedVolatility, openInterest,
      volume, expiration, option_type
    """
    # 1. Alpaca option chain
    client = _get_options_client()
    if client and expirations:
        try:
            from alpaca.data import OptionChainRequest
            exp_dates = sorted(expirations)
            req = OptionChainRequest(
                underlying_symbol=symbol,
                expiration_date_gte=exp_dates[0],
                expiration_date_lte=exp_dates[-1],
                type="put",
            )
            chain = client.get_option_chain(req)
            if chain:
                rows = []
                for occ_sym, snap in chain.items():
                    # Filter to only requested expirations
                    exp_str = _exp_from_occ(occ_sym, symbol)
                    if exp_str not in expirations:
                        continue
                    q = snap.latest_quote
                    g = snap.greeks
                    if q is None:
                        continue
                    bid = float(q.bid_price or 0)
                    ask = float(q.ask_price or 0)
                    if bid <= 0 and ask <= 0:
                        continue
                    rows.append({
                        "contractSymbol":    occ_sym,
                        "strike":            _strike_from_occ(occ_sym, symbol),
                        "bid":               bid,
                        "ask":               ask,
                        "lastPrice":         float(getattr(snap.latest_trade, "price", 0) or 0),
                        "delta":             float(g.delta) if g and g.delta is not None else None,
                        "theta":             float(g.theta) if g and g.theta is not None else None,
                        "gamma":             float(g.gamma) if g and g.gamma is not None else None,
                        "vega":              float(g.vega)  if g and g.vega  is not None else None,
                        "impliedVolatility": float(snap.implied_volatility) if snap.implied_volatility else None,
                        "openInterest":      int(getattr(q, "ask_size", 0) or 0),  # OI not in snapshot
                        "volume":            0,
                        "expiration":        exp_str,
                        "option_type":       "put",
                    })
                if rows:
                    df = pd.DataFrame(rows)
                    logger.info("options for %s via Alpaca: %d puts", symbol, len(df))
                    return df
        except Exception as exc:
            logger.warning("Alpaca options chain failed for %s: %s", symbol, exc)

    # 2. yfinance fallback
    try:
        from scanner.yf_session import ticker as yf_ticker
        from options_scanner import with_retry
        t = yf_ticker(symbol)
        frames = []
        for exp in expirations:
            try:
                puts = with_retry(lambda e=exp: t.option_chain(e).puts)
                if not puts.empty:
                    puts = puts.copy()
                    puts["expiration"] = exp
                    puts["option_type"] = "put"
                    frames.append(puts)
            except Exception:
                pass
        if frames:
            logger.debug("options for %s via yfinance fallback", symbol)
            return pd.concat(frames, ignore_index=True)
    except Exception as exc:
        logger.warning("yfinance options fallback for %s: %s", symbol, exc)

    return None


def get_calls_chain(symbol: str, expirations: List[str] = None) -> Optional[pd.DataFrame]:
    """
    Return CALL option chain for all listed expirations as one DataFrame.
    Tries: Alpaca option snapshots → yfinance.

    Output columns (normalised):
      strike, bid, ask, delta, theta, impliedVolatility, openInterest,
      volume, expiration, option_type

    Used by Wheel strategy to find calls for covered call leg after assignment.
    """
    # Get available expirations if not provided
    if expirations is None:
        expirations = get_option_expirations(symbol)

    if not expirations:
        logger.warning("No expirations for %s", symbol)
        return None

    # 1. Alpaca option chain
    client = _get_options_client()
    if client and expirations:
        try:
            from alpaca.data import OptionChainRequest
            exp_dates = sorted(expirations)
            req = OptionChainRequest(
                underlying_symbol=symbol,
                expiration_date_gte=exp_dates[0],
                expiration_date_lte=exp_dates[-1],
                type="call",
            )
            chain = client.get_option_chain(req)
            if chain:
                rows = []
                for occ_sym, snap in chain.items():
                    # Filter to only requested expirations
                    exp_str = _exp_from_occ(occ_sym, symbol)
                    if exp_str not in expirations:
                        continue
                    q = snap.latest_quote
                    g = snap.greeks
                    if q is None:
                        continue
                    bid = float(q.bid_price or 0)
                    ask = float(q.ask_price or 0)
                    if bid <= 0 and ask <= 0:
                        continue
                    rows.append({
                        "contractSymbol":    occ_sym,
                        "strike":            _strike_from_occ(occ_sym, symbol),
                        "bid":               bid,
                        "ask":               ask,
                        "lastPrice":         float(getattr(snap.latest_trade, "price", 0) or 0),
                        "delta":             float(g.delta) if g and g.delta is not None else None,
                        "theta":             float(g.theta) if g and g.theta is not None else None,
                        "gamma":             float(g.gamma) if g and g.gamma is not None else None,
                        "vega":              float(g.vega)  if g and g.vega  is not None else None,
                        "rho":               float(g.rho)   if g and g.rho   is not None else None,
                        "impliedVolatility": float(g.vega / 39.447) if g and g.vega else None,  # IV approximation
                        "openInterest":      int(snap.open_interest or 0),
                        "volume":            0,  # Not provided by Alpaca
                        "expiration":        exp_str,
                        "option_type":       "call",
                    })
                if rows:
                    logger.debug("calls for %s via Alpaca", symbol)
                    return pd.DataFrame(rows)
        except Exception as exc:
            logger.warning("Alpaca options error for %s: %s", symbol, exc)

    # 2. yfinance fallback (same structure as puts)
    try:
        frames = []
        for exp_str in expirations:
            try:
                yf_data = yf_ticker(symbol)
                options_df = yf_data.option_chain(exp_str).calls
                if options_df is None or options_df.empty:
                    continue
                options_df["expiration"] = exp_str
                options_df["option_type"] = "call"
                frames.append(options_df)
            except Exception as exc:
                logger.debug("yfinance call chain error for %s exp %s: %s", symbol, exp_str, exc)
        if frames:
            logger.debug("calls for %s via yfinance fallback", symbol)
            return pd.concat(frames, ignore_index=True)
    except Exception as exc:
        logger.warning("yfinance call fallback for %s: %s", symbol, exc)

    return None


# ── OCC symbol helpers ────────────────────────────────────────────────────────

def _exp_from_occ(occ_sym: str, underlying: str) -> str:
    """Extract YYYY-MM-DD expiration from OCC symbol e.g. AAPL260815P00280000."""
    try:
        date_part = occ_sym[len(underlying):len(underlying)+6]  # YYMMDD
        d = datetime.datetime.strptime(date_part, "%y%m%d").date()
        return d.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _strike_from_occ(occ_sym: str, underlying: str) -> float:
    """Extract strike price from OCC symbol e.g. AAPL260815P00280000 → 280.0."""
    try:
        # Last 8 digits before end = strike × 1000
        strike_str = occ_sym[-8:]
        return int(strike_str) / 1000.0
    except Exception:
        return 0.0
