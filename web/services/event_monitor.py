"""
event_monitor.py
----------------
Background engine that polls all event providers on an interval, deduplicates
and persists new events, matches them against enabled alert rules, and
dispatches notifications.

Modeled on the existing scan-thread pattern in ``web/app.py``: a daemon thread
plus a lock-protected ``_monitor_state`` dict exposed to the API. One provider
failing never kills the loop — each source is wrapped independently.

Configuration (data/credentials.json / env, optional):
  poll_interval_seconds   default 60   (clamped to >= 30)
  price_move_pct          default 3.0  (unusual-move price threshold)
  volume_multiple         default 2.0  (unusual-move volume threshold)
  news_max_age_minutes    default 120
"""

from __future__ import annotations

import os
import json
import time
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scanner import event_providers as ep
from web.database import get_db_session
from web.repositories.event_repository import EventRepository
from web.services import notification_service as ns

logger = logging.getLogger(__name__)

_CREDS_FILE = Path(__file__).parent.parent.parent / "data" / "credentials.json"

_monitor_lock = threading.Lock()
_monitor_state: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "last_tick": None,
    "last_error": None,
    "events_today": 0,
    "ticks": 0,
}
_monitor_thread: threading.Thread | None = None
_stop_flag = threading.Event()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settings() -> Dict[str, Any]:
    """Read tunables from credentials.json with sane defaults + env override."""
    creds: Dict[str, Any] = {}
    if _CREDS_FILE.exists():
        try:
            creds = json.loads(_CREDS_FILE.read_text())
        except Exception:
            pass

    def _num(key: str, default: float) -> float:
        val = os.getenv(key.upper()) or creds.get(key)
        try:
            return float(val) if val is not None and val != "" else default
        except (TypeError, ValueError):
            return default

    interval = max(30.0, _num("poll_interval_seconds", 60.0))
    return {
        "poll_interval_seconds": interval,
        "price_move_pct": _num("price_move_pct", 3.0),
        "volume_multiple": _num("volume_multiple", 2.0),
        "news_max_age_minutes": _num("news_max_age_minutes", 120.0),
    }


def _active_watchlist(repo: EventRepository) -> List[str]:
    """Union of symbols across all enabled rules — what news/moves should track."""
    symbols: set[str] = set()
    for rule in repo.list_rules(enabled_only=True):
        symbols.update(rule.get_symbols())
    return sorted(symbols)


def _collect_events(repo: EventRepository, settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Poll every provider, each isolated so one failure can't sink the rest."""
    collected: List[Dict[str, Any]] = []
    watchlist = _active_watchlist(repo)

    sources = [
        ("economic", lambda: ep.get_economic_events()),
        ("news", lambda: ep.get_market_news(
            symbols=watchlist or None,
            max_age_minutes=int(settings["news_max_age_minutes"]),
        )),
        ("unusual_move", lambda: ep.detect_unusual_moves(
            watchlist,
            price_move_pct=settings["price_move_pct"],
            volume_multiple=settings["volume_multiple"],
        )),
        ("political", lambda: ep.get_political_posts()),
    ]
    for name, fn in sources:
        try:
            collected.extend(fn() or [])
        except Exception as exc:
            logger.warning("Provider %s failed this tick: %s", name, exc)
    return collected


def _process_event(repo: EventRepository, event_data: Dict[str, Any]) -> None:
    """Persist a (deduped) event and dispatch to every matching rule's channels."""
    event = repo.create_event(event_data)
    if event is None:
        return  # duplicate or write error — already logged

    event_dict = event.to_dict()
    rules = repo.list_rules(enabled_only=True)

    # Collect the union of channels across all matching rules, attributing the
    # delivery to the first matching rule (audit trail). If no rule matches, the
    # event is still stored and visible in-app, just not pushed externally.
    matched_rule_id = None
    channels: List[str] = []
    for rule in rules:
        if rule.matches(event):
            if matched_rule_id is None:
                matched_rule_id = rule.id
            channels.extend(rule.get_channels())

    if not channels:
        return

    ns.dispatch(event_dict, channels, repo, rule_id=matched_rule_id)


def _tick() -> None:
    """One polling cycle."""
    db = get_db_session()
    try:
        repo = EventRepository(db)
        settings = _settings()
        for event_data in _collect_events(repo, settings):
            try:
                _process_event(repo, event_data)
            except Exception as exc:
                logger.warning("Failed to process an event: %s", exc)

        with _monitor_lock:
            _monitor_state["last_tick"] = _iso_now()
            _monitor_state["last_error"] = None
            _monitor_state["events_today"] = repo.count_events_today()
            _monitor_state["ticks"] += 1
    finally:
        db.close()


def _run_loop() -> None:
    logger.info("Event monitor loop started")
    with _monitor_lock:
        _monitor_state["running"] = True
        _monitor_state["started_at"] = _iso_now()

    while not _stop_flag.is_set():
        try:
            _tick()
        except Exception as exc:
            logger.error("Monitor tick crashed: %s", exc)
            with _monitor_lock:
                _monitor_state["last_error"] = str(exc)
        # Sleep in small slices so stop() is responsive.
        interval = _settings()["poll_interval_seconds"]
        slept = 0.0
        while slept < interval and not _stop_flag.is_set():
            time.sleep(min(2.0, interval - slept))
            slept += 2.0

    with _monitor_lock:
        _monitor_state["running"] = False
    logger.info("Event monitor loop stopped")


def start_monitor() -> bool:
    """
    Start the background monitor if any event source is configured. No-ops (and
    returns False) when nothing is configured, so startup stays quiet until the
    user adds credentials.
    """
    global _monitor_thread

    status = ep.provider_status()
    if not any(status.values()):
        logger.info("Event monitor not started: no event sources configured")
        return False

    with _monitor_lock:
        if _monitor_state["running"]:
            return True

    _stop_flag.clear()
    _monitor_thread = threading.Thread(target=_run_loop, daemon=True, name="event-monitor")
    _monitor_thread.start()
    return True


def stop_monitor() -> None:
    _stop_flag.set()


def get_state() -> Dict[str, Any]:
    with _monitor_lock:
        state = dict(_monitor_state)
    state["providers"] = ep.provider_status()
    state["channels"] = ns.channel_status()
    return state


def run_test_alert(repo: EventRepository, channels: List[str]) -> Dict[str, Any]:
    """
    Fire a synthetic event through the given channels so the user can confirm
    Telegram / desktop work. Persists a real (test-source) MarketEvent.
    """
    test_data = {
        "event_type": "test",
        "source": "test",
        "symbol": "TEST",
        "severity": "high",
        "title": "Test alert from Trading Alerts",
        "body": "If you see this on your selected channels, notifications work.",
        "url": None,
        "dedup_parts": ["test", _iso_now()],  # unique each time
    }
    event = repo.create_event(test_data)
    if event is None:
        return {"error": "Failed to create test event"}
    results = ns.dispatch(event.to_dict(), channels, repo, rule_id=None)
    return {"event": event.to_dict(), "results": results}
