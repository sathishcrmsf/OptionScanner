"""
yf_session.py
-------------
A single shared, browser-impersonating HTTP session for ALL yfinance calls.

Why this exists
===============
yfinance talks to Yahoo's undocumented JSON endpoints. Yahoo aggressively
rate-limits unauthenticated request *bursts* — and a full scan fires many
separate requests per symbol (``.info``, ``.history``, ``.calendar``,
``.options``, ``.option_chain``) across 500+ symbols. With a fresh connection
per call and no browser-like headers, Yahoo returns ``429 Too Many Requests``
almost immediately and the whole scan comes back empty.

The fix (recommended by yfinance ≥ 0.2.52) is to pass a shared
``curl_cffi`` session that *impersonates a real Chrome browser*. This:

* reuses one keep-alive connection (no per-call TCP/TLS handshake),
* sends a genuine browser TLS fingerprint + headers (defeats the bot filter),
* lets every ``yf.Ticker(...)`` share the same warmed-up cookie/crumb.

Usage
=====
    from scanner.yf_session import ticker, get_session

    t = ticker("AAPL")          # == yf.Ticker("AAPL", session=<shared>)
    hist = t.history(period="60d")

Always construct Tickers via ``ticker()`` (or pass ``session=get_session()``)
so every call rides the same impersonating session.
"""

from __future__ import annotations

import logging
import threading

import yfinance as yf

logger = logging.getLogger(__name__)

# Chrome build to impersonate. curl_cffi ships fingerprints for several
# browsers; a recent Chrome is the safest default for Yahoo.
_IMPERSONATE = "chrome"

_session = None
_lock = threading.Lock()


def get_session():
    """
    Return the process-wide shared yfinance HTTP session.

    Lazily creates a ``curl_cffi`` session that impersonates Chrome. If
    ``curl_cffi`` is unavailable for any reason, returns ``None`` so callers
    fall back to yfinance's default session (degraded, but never crashes).
    """
    global _session
    if _session is not None:
        return _session

    with _lock:
        if _session is not None:
            return _session
        try:
            from curl_cffi import requests as curl_requests

            _session = curl_requests.Session(impersonate=_IMPERSONATE)
            logger.info("yfinance: using shared curl_cffi session (impersonate=%s)", _IMPERSONATE)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "yfinance: curl_cffi session unavailable (%s); "
                "falling back to default session — expect rate limits", exc
            )
            _session = None
    return _session


def ticker(symbol: str) -> "yf.Ticker":
    """Build a ``yf.Ticker`` bound to the shared impersonating session."""
    sess = get_session()
    if sess is not None:
        return yf.Ticker(symbol, session=sess)
    return yf.Ticker(symbol)
