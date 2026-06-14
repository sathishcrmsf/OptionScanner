"""
event_providers.py
------------------
Pulls market-moving events from external sources for the alerting layer.

Sources
=======
1. **Finnhub**  — economic calendar (CPI/FOMC/jobs/GDP) + market/company news.
                  Free tier, one token. https://finnhub.io/
2. **Alpaca**   — reused from ``scanner.data_providers`` to detect unusual
                  price/volume moves on a watchlist (no extra API key).
3. **Political feed** — pluggable: a configurable RSS/JSON URL (e.g. a Truth
                  Social / X bridge you control). Best-effort; returns [] when
                  unset or unreachable, never raising into the monitor loop.

Credentials  (same file + env pattern as data_providers.py)
===========
Loaded from, in order:
  1. data/credentials.json   (git-ignored, set via the Alerts settings UI)
  2. Environment variables:  FINNHUB_TOKEN, POLITICAL_FEED_URL

data/credentials.json keys used here:
  {
    "finnhub_token":      "xxxxxxxxxxxxxxxxxxxx",
    "political_feed_url": "https://.../feed.json"   # optional
  }

Every public function returns a list of plain dicts shaped for
``MarketEvent.from_dict`` (keys: event_type, source, title; optional symbol,
severity, body, url, dedup_parts, detected_at) and swallows its own errors so a
single failing source can never take down the monitor.
"""

from __future__ import annotations

import json
import logging
import os
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_CREDS_FILE = Path(__file__).parent.parent / "data" / "credentials.json"

FINNHUB_BASE = "https://finnhub.io/api/v1"
_HTTP_TIMEOUT = 10  # seconds


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


def get_finnhub_token() -> str:
    creds = _load_credentials()
    return os.getenv("FINNHUB_TOKEN") or creds.get("finnhub_token", "")


def is_finnhub_configured() -> bool:
    return bool(get_finnhub_token())


def get_political_feed_url() -> str:
    creds = _load_credentials()
    return os.getenv("POLITICAL_FEED_URL") or creds.get("political_feed_url", "")


def is_political_configured() -> bool:
    return bool(get_political_feed_url())


def _finnhub_get(path: str, params: Dict[str, Any]) -> Optional[Any]:
    """GET a Finnhub endpoint; returns parsed JSON or None on any failure."""
    token = get_finnhub_token()
    if not token:
        return None
    try:
        params = {**params, "token": token}
        resp = requests.get(f"{FINNHUB_BASE}{path}", params=params, timeout=_HTTP_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("Finnhub %s returned HTTP %s", path, resp.status_code)
            return None
        return resp.json()
    except Exception as exc:
        logger.warning("Finnhub request %s failed: %s", path, exc)
        return None


# ── Economic calendar ─────────────────────────────────────────────────────────

# Finnhub impact strings → our severity buckets.
_IMPACT_SEVERITY = {"3": "high", "high": "high", "2": "medium", "medium": "medium",
                    "1": "low", "low": "low"}

# Keywords that mark a calendar item as high-impact even if the API understates it.
_HIGH_IMPACT_KEYWORDS = ("cpi", "fomc", "fed funds", "interest rate", "nonfarm",
                         "non-farm", "unemployment", "gdp", "pce", "ppi", "fed ")


def get_economic_events(window_days: int = 2) -> List[Dict[str, Any]]:
    """
    Upcoming / just-released US economic-calendar items within +/- window_days.
    Returns event dicts; [] if Finnhub isn't configured or returns nothing.
    """
    if not is_finnhub_configured():
        return []

    today = datetime.date.today()
    frm = (today - datetime.timedelta(days=window_days)).isoformat()
    to = (today + datetime.timedelta(days=window_days)).isoformat()

    data = _finnhub_get("/calendar/economic", {"from": frm, "to": to})
    if not data:
        return []

    items = data.get("economicCalendar", []) if isinstance(data, dict) else []
    events: List[Dict[str, Any]] = []
    for it in items:
        try:
            country = str(it.get("country", "")).upper()
            if country and country not in ("US", "USA", "UNITED STATES"):
                continue  # focus on US macro for now

            name = str(it.get("event", "")).strip()
            if not name:
                continue

            impact = str(it.get("impact", "")).lower()
            severity = _IMPACT_SEVERITY.get(impact, "low")
            if any(kw in name.lower() for kw in _HIGH_IMPACT_KEYWORDS):
                severity = "high"

            when = str(it.get("time", "")) or str(it.get("date", ""))
            actual = it.get("actual")
            estimate = it.get("estimate")
            body_parts = [f"When: {when}"]
            if estimate is not None:
                body_parts.append(f"Estimate: {estimate}")
            if actual is not None:
                body_parts.append(f"Actual: {actual}")

            events.append({
                "event_type": "economic",
                "source": "finnhub",
                "symbol": None,
                "severity": severity,
                "title": name,
                "body": " | ".join(body_parts),
                "url": "https://finnhub.io/",
                # Dedup on the specific event + scheduled time so a re-poll of
                # the same calendar entry doesn't re-alert.
                "dedup_parts": ["econ", name, when],
            })
        except Exception as exc:
            logger.debug("Skipping malformed calendar item: %s", exc)
    logger.info("Economic calendar: %d events in window", len(events))
    return events


# ── Market / company news ─────────────────────────────────────────────────────

def get_market_news(
    symbols: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    max_age_minutes: int = 120,
) -> List[Dict[str, Any]]:
    """
    Recent news headlines. If ``symbols`` is given, fetch company-news for each;
    otherwise fetch general market news. Optionally filter by ``keywords``.
    Only returns items newer than ``max_age_minutes`` to avoid re-surfacing
    stale headlines on every poll.
    """
    if not is_finnhub_configured():
        return []

    symbols = [s.upper() for s in (symbols or [])]
    keywords = [k.lower() for k in (keywords or [])]
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=max_age_minutes)
    events: List[Dict[str, Any]] = []

    raw_items: List[Dict[str, Any]] = []
    if symbols:
        today = datetime.date.today()
        frm = (today - datetime.timedelta(days=1)).isoformat()
        to = today.isoformat()
        for sym in symbols[:15]:  # be gentle on the free tier
            data = _finnhub_get("/company-news", {"symbol": sym, "from": frm, "to": to})
            if isinstance(data, list):
                for it in data:
                    it["_symbol"] = sym
                    raw_items.append(it)
    else:
        data = _finnhub_get("/news", {"category": "general"})
        if isinstance(data, list):
            raw_items = data

    for it in raw_items:
        try:
            headline = str(it.get("headline", "")).strip()
            if not headline:
                continue

            ts = it.get("datetime")
            published = (
                datetime.datetime.utcfromtimestamp(int(ts))
                if ts else datetime.datetime.utcnow()
            )
            if published < cutoff:
                continue

            summary = str(it.get("summary", ""))
            if keywords:
                haystack = f"{headline} {summary}".lower()
                if not any(kw in haystack for kw in keywords):
                    continue

            # Headlines naming macro/political triggers get bumped to high.
            severity = "medium"
            if any(kw in headline.lower() for kw in _HIGH_IMPACT_KEYWORDS + ("trump", "tariff")):
                severity = "high"

            events.append({
                "event_type": "news",
                "source": "finnhub",
                "symbol": it.get("_symbol"),
                "severity": severity,
                "title": headline[:300],
                "body": summary[:1000] if summary else None,
                "url": it.get("url"),
                "dedup_parts": ["news", str(it.get("id") or headline)],
                "detected_at": published.isoformat(),
            })
        except Exception as exc:
            logger.debug("Skipping malformed news item: %s", exc)

    logger.info("Market news: %d fresh headlines", len(events))
    return events


# ── Unusual price / volume moves (reuses Alpaca via data_providers) ───────────

def detect_unusual_moves(
    symbols: List[str],
    price_move_pct: float = 3.0,
    volume_multiple: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    Flag watchlist symbols whose latest daily move exceeds ``price_move_pct`` %
    or whose volume is ``volume_multiple``x the recent average.

    Reuses ``scanner.data_providers.get_ohlcv_history`` so it needs no new API.
    """
    if not symbols:
        return []

    try:
        from scanner.data_providers import get_ohlcv_history
    except Exception as exc:
        logger.warning("Cannot import data_providers for unusual-move detection: %s", exc)
        return []

    events: List[Dict[str, Any]] = []
    for sym in symbols:
        sym = sym.upper()
        try:
            df = get_ohlcv_history(sym, days=30)
            if df is None or len(df) < 5:
                continue

            last = df.iloc[-1]
            prev_close = float(df["Close"].iloc[-2])
            last_close = float(last["Close"])
            if prev_close <= 0:
                continue

            move_pct = (last_close - prev_close) / prev_close * 100.0

            avg_vol = float(df["Volume"].iloc[:-1].tail(20).mean() or 0)
            last_vol = float(last["Volume"])
            vol_mult = (last_vol / avg_vol) if avg_vol > 0 else 0.0

            price_hit = abs(move_pct) >= price_move_pct
            vol_hit = vol_mult >= volume_multiple
            if not (price_hit or vol_hit):
                continue

            # Severity scales with how extreme the move is.
            severity = "medium"
            if abs(move_pct) >= price_move_pct * 2 or vol_mult >= volume_multiple * 2:
                severity = "high"

            direction = "up" if move_pct >= 0 else "down"
            title = f"{sym} moved {move_pct:+.1f}% ({direction})"
            body_parts = [f"Close {prev_close:.2f} → {last_close:.2f}"]
            if vol_hit:
                body_parts.append(f"Volume {vol_mult:.1f}x 20-day avg")
            # Dedup per symbol per day so we alert once per trading day, not every tick.
            today_key = datetime.date.today().isoformat()

            events.append({
                "event_type": "unusual_move",
                "source": "alpaca",
                "symbol": sym,
                "severity": severity,
                "title": title,
                "body": " | ".join(body_parts),
                "url": None,
                "dedup_parts": ["move", sym, today_key],
            })
        except Exception as exc:
            logger.debug("Unusual-move check failed for %s: %s", sym, exc)

    logger.info("Unusual moves: %d flagged of %d symbols", len(events), len(symbols))
    return events


# ── Political feed (pluggable, best-effort) ──────────────────────────────────

def get_political_posts(max_items: int = 10) -> List[Dict[str, Any]]:
    """
    Read political/market-moving posts from a configured RSS/JSON bridge URL.

    Supported shapes (auto-detected):
      - JSON list:  [{"id"|"title"|"text"|"content", "url"?, "date"?}, ...]
      - JSON dict:  {"items"|"posts"|"data": [ ...same... ]}

    Returns [] (logging a warning) when unset or unreachable — by design this
    must never raise into the monitor loop. RSS/XML feeds are out of scope here
    and should be exposed as JSON by the bridge.
    """
    url = get_political_feed_url()
    if not url:
        return []

    try:
        resp = requests.get(url, timeout=_HTTP_TIMEOUT, headers={"User-Agent": "trading-alerts/1.0"})
        if resp.status_code != 200:
            logger.warning("Political feed returned HTTP %s", resp.status_code)
            return []
        payload = resp.json()
    except Exception as exc:
        logger.warning("Political feed fetch/parse failed: %s", exc)
        return []

    # Normalise to a list of item dicts.
    items: List[Dict[str, Any]] = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("items", "posts", "data", "results"):
            if isinstance(payload.get(key), list):
                items = payload[key]
                break

    events: List[Dict[str, Any]] = []
    for it in items[:max_items]:
        try:
            if not isinstance(it, dict):
                # Plain string post
                text = str(it).strip()
                ident = text
                post_url = url
                date = None
            else:
                text = str(
                    it.get("text") or it.get("content") or it.get("title") or ""
                ).strip()
                ident = str(it.get("id") or text)
                post_url = it.get("url")
                date = it.get("date") or it.get("created_at")

            if not text:
                continue

            detected = None
            if date:
                try:
                    detected = datetime.datetime.fromisoformat(str(date).replace("Z", "+00:00")).isoformat()
                except Exception:
                    detected = None

            events.append({
                "event_type": "political",
                "source": "political_feed",
                "symbol": None,
                "severity": "high",  # political posts treated as high by default
                "title": text[:300],
                "body": text if len(text) > 300 else None,
                "url": post_url,
                "dedup_parts": ["political", ident],
                "detected_at": detected,
            })
        except Exception as exc:
            logger.debug("Skipping malformed political item: %s", exc)

    logger.info("Political feed: %d posts", len(events))
    return events


# ── Aggregate status (for the settings UI / monitor) ─────────────────────────

def provider_status() -> Dict[str, bool]:
    """Which event sources are currently configured/usable."""
    from scanner.data_providers import is_alpaca_configured
    return {
        "finnhub": is_finnhub_configured(),      # economic + news
        "alpaca": is_alpaca_configured(),        # unusual moves
        "political": is_political_configured(),  # political feed
    }
