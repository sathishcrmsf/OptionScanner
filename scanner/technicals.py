"""
technicals.py
-------------
Per-ticker Pivot Points (1D / 1W / 1M) and Bollinger Bands (20-period, ±2σ)
for the CSP Scanner.

All calculations use daily OHLCV data from yfinance (60 days of history —
enough for 20-period BB and complete 1W / 1M pivot candles).

Results are cached in a module-level dict for the duration of a scan run.
Call reset_tech_cache() at the start of each scan to flush stale data.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Module-level cache: symbol → computed technicals dict.
# Populated lazily; flushed by reset_tech_cache() at scan start.
_tech_cache: Dict[str, Dict[str, Any]] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pivot_from_candle(h: float, l: float, c: float) -> Dict[str, float]:
    """Standard (floor-trader) pivot points from a single OHLC candle."""
    pp = (h + l + c) / 3.0
    r1 = 2 * pp - l
    r2 = pp + (h - l)
    r3 = h + 2 * (pp - l)
    s1 = 2 * pp - h
    s2 = pp - (h - l)
    s3 = l - 2 * (h - pp)
    return {
        "pp": round(pp, 2),
        "r1": round(r1, 2), "r2": round(r2, 2), "r3": round(r3, 2),
        "s1": round(s1, 2), "s2": round(s2, 2), "s3": round(s3, 2),
    }


def _empty_technicals() -> Dict[str, Any]:
    """Return a zeroed-out technicals dict for symbols where data is unavailable."""
    return {
        "pivot_1d": {},
        "pivot_1w": {},
        "pivot_1m": {},
        "bb_upper":     None,
        "bb_middle":    None,
        "bb_lower":     None,
        "bb_width_pct": None,
        "bb_pct_b":     None,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def reset_tech_cache() -> None:
    """Flush the per-scan cache. Call once at the start of each scan run."""
    _tech_cache.clear()


def get_technicals(symbol: str, current_price: float) -> Dict[str, Any]:
    """
    Fetch (or return cached) pivot points and Bollinger Band data for *symbol*.

    Fetches 60 calendar days of daily OHLCV — enough for:
    - 1D pivot: previous trading day's candle
    - 1W pivot: most recent completed week (W-FRI resample)
    - 1M pivot: most recent completed month (ME resample)
    - 20-day Bollinger Bands

    Returns
    -------
    dict with keys:
        pivot_1d, pivot_1w, pivot_1m : dict of {pp, r1, r2, r3, s1, s2, s3}
        bb_upper, bb_middle, bb_lower : float
        bb_width_pct : float  (band width as % of mid-price)
        bb_pct_b     : float  (0=lower band, 1=upper band)
    """
    if symbol in _tech_cache:
        return _tech_cache[symbol]

    result = _empty_technicals()

    try:
        from scanner.data_providers import get_ohlcv_history
        hist = get_ohlcv_history(symbol, days=65)

        if hist is None or hist.empty or len(hist) < 21:
            logger.debug("technicals: insufficient history for %s (%d bars)", symbol, len(hist))
            _tech_cache[symbol] = result
            return result

        # ── 1D pivot: previous trading-day candle ───────────────────────────
        prev = hist.iloc[-2]
        result["pivot_1d"] = _pivot_from_candle(
            float(prev["High"]), float(prev["Low"]), float(prev["Close"])
        )

        # ── 1W pivot: most recent *completed* week (Mon–Fri) ────────────────
        # Resample to week-ending Friday; drop the current (incomplete) week
        weekly = (
            hist
            .resample("W-FRI")
            .agg({"High": "max", "Low": "min", "Close": "last"})
            .dropna()
        )
        if len(weekly) >= 2:
            w = weekly.iloc[-2]
            result["pivot_1w"] = _pivot_from_candle(
                float(w["High"]), float(w["Low"]), float(w["Close"])
            )

        # ── 1M pivot: most recent *completed* month ──────────────────────────
        monthly = (
            hist
            .resample("ME")
            .agg({"High": "max", "Low": "min", "Close": "last"})
            .dropna()
        )
        if len(monthly) >= 2:
            m = monthly.iloc[-2]
            result["pivot_1m"] = _pivot_from_candle(
                float(m["High"]), float(m["Low"]), float(m["Close"])
            )

        # ── Bollinger Bands (20-period, ±2σ) ────────────────────────────────
        closes = hist["Close"].astype(float)
        sma20 = closes.rolling(20).mean().iloc[-1]
        std20 = closes.rolling(20).std().iloc[-1]

        if pd.notna(sma20) and pd.notna(std20) and sma20 > 0:
            bb_upper = sma20 + 2.0 * std20
            bb_lower = sma20 - 2.0 * std20
            bb_range = bb_upper - bb_lower

            result["bb_upper"]  = round(float(bb_upper), 2)
            result["bb_middle"] = round(float(sma20), 2)
            result["bb_lower"]  = round(float(bb_lower), 2)
            result["bb_width_pct"] = round(float(bb_range / sma20 * 100), 1) if sma20 > 0 else None
            result["bb_pct_b"]  = (
                round(float((current_price - bb_lower) / bb_range), 3)
                if bb_range > 0 else 0.5
            )

    except Exception as exc:  # noqa: BLE001
        logger.warning("technicals: failed for %s — %s", symbol, exc)

    _tech_cache[symbol] = result
    return result


def tech_score(technicals: Dict[str, Any], strike: float, current_price: float) -> Optional[int]:
    """
    Compute a 0–100 Technical Context Score for a CSP at *strike*.

    Scoring logic (professional CSP entry criteria):

    Strike vs Weekly Pivots (30 pts)
        strike < weekly S2     → 30 pts  (strike in very safe zone)
        strike < weekly S1     → 18 pts  (acceptable cushion)
        strike < weekly PP     →  6 pts  (marginal — only PP as buffer)

    Price vs Weekly Pivot (25 pts)
        price > weekly PP      → 25 pts  (price in weekly uptrend)
        price > weekly S1      → 10 pts  (holding above first support)

    Price vs Monthly Pivot (20 pts)
        price > monthly PP     → 20 pts  (monthly uptrend intact)
        price > monthly S1     →  8 pts  (above monthly first support)

    BB %B position (15 pts)
        0.30 ≤ %B ≤ 0.70      → 15 pts  (price in mid-band = stable)
        0.20 ≤ %B < 0.30      →  8 pts  (approaching lower band)
        0.70 < %B ≤ 0.80      →  8 pts  (approaching upper band)
        %B < 0.20 or > 0.80   →  0 pts  (oversold/overbought extreme)

    BB Width regime (10 pts)
        width < 10%            → 10 pts  (squeeze = stable low-vol regime)
        10% ≤ width < 20%      →  6 pts  (normal)
        20% ≤ width < 30%      →  3 pts  (expanding, caution)
        width ≥ 30%            →  0 pts  (high vol, directional move)

    Returns None if no technical data is available.
    """
    w = technicals.get("pivot_1w") or {}
    m = technicals.get("pivot_1m") or {}

    # If we have no pivot data at all, return None (scanner still shows row)
    if not w and not m:
        return None

    score = 0

    # ── Strike vs weekly S1/S2 (30 pts) ──────────────────────────────────────
    if w:
        w_s2 = w.get("s2")
        w_s1 = w.get("s1")
        w_pp = w.get("pp")
        if w_s2 is not None and strike < w_s2:
            score += 30
        elif w_s1 is not None and strike < w_s1:
            score += 18
        elif w_pp is not None and strike < w_pp:
            score += 6

    # ── Price vs weekly pivot (25 pts) ────────────────────────────────────────
    if w:
        w_pp  = w.get("pp")
        w_s1  = w.get("s1")
        if w_pp is not None and current_price > w_pp:
            score += 25
        elif w_s1 is not None and current_price > w_s1:
            score += 10

    # ── Price vs monthly pivot (20 pts) ──────────────────────────────────────
    if m:
        m_pp = m.get("pp")
        m_s1 = m.get("s1")
        if m_pp is not None and current_price > m_pp:
            score += 20
        elif m_s1 is not None and current_price > m_s1:
            score += 8

    # ── BB %B (15 pts) ────────────────────────────────────────────────────────
    pct_b = technicals.get("bb_pct_b")
    if pct_b is not None:
        if 0.30 <= pct_b <= 0.70:
            score += 15
        elif 0.20 <= pct_b < 0.30 or 0.70 < pct_b <= 0.80:
            score += 8
        # else: < 0.20 or > 0.80 → 0 pts (oversold/overbought extreme)

    # ── BB Width (10 pts) ─────────────────────────────────────────────────────
    width = technicals.get("bb_width_pct")
    if width is not None:
        if width < 10:
            score += 10
        elif width < 20:
            score += 6
        elif width < 30:
            score += 3
        # else: ≥ 30 → 0 pts

    return min(score, 100)


# ── CLI smoke test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    ticker_sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    price = float(sys.argv[2]) if len(sys.argv) > 2 else 210.0
    strike = float(sys.argv[3]) if len(sys.argv) > 3 else 190.0

    t = get_technicals(ticker_sym, price)
    score = tech_score(t, strike, price)

    print(f"\n=== {ticker_sym} @ ${price:.2f} | Strike ${strike:.2f} ===")
    for tf, label in [("pivot_1d", "Daily"), ("pivot_1w", "Weekly"), ("pivot_1m", "Monthly")]:
        pv = t.get(tf, {})
        if pv:
            print(f"\n{label} Pivots:")
            print(f"  PP={pv['pp']}  R1={pv['r1']}  R2={pv['r2']}")
            print(f"  S1={pv['s1']}  S2={pv['s2']}  S3={pv['s3']}")

    print(f"\nBollinger Bands (20/2):")
    print(f"  Upper={t['bb_upper']}  Mid={t['bb_middle']}  Lower={t['bb_lower']}")
    print(f"  Width={t['bb_width_pct']}%  %B={t['bb_pct_b']}")
    print(f"\nTech Score: {score}/100")
