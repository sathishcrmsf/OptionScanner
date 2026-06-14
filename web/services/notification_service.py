"""
Notification service — delivers alerts to the user's chosen channels.

Channels
========
- ``in_app``   — no send step; the persisted MarketEvent is surfaced by /api/events.
                 We still record an AlertDelivery row so the audit trail is complete.
- ``telegram`` — HTTP POST to the Telegram Bot API (needs bot token + chat id).
- ``desktop``  — macOS native notification via ``osascript`` (local only).

Credentials come from data/credentials.json / env vars (same pattern as the
data + event providers): telegram_bot_token, telegram_chat_id.

``dispatch(event, channels, repo, rule_id)`` fans an event out to the given
channels, records every attempt (sent/failed/skipped) via the repository, and
never raises — a failing channel must not break the monitor loop.
"""

from __future__ import annotations

import os
import json
import shutil
import logging
import platform
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_CREDS_FILE = Path(__file__).parent.parent.parent / "data" / "credentials.json"
_HTTP_TIMEOUT = 10

SEVERITY_EMOJI = {"high": "🔴", "medium": "🟠", "low": "🟢"}
EVENT_EMOJI = {
    "economic": "📅",
    "news": "📰",
    "unusual_move": "📈",
    "political": "🗣️",
    "test": "🧪",
}


# ── Credentials ───────────────────────────────────────────────────────────────

def _load_credentials() -> Dict:
    if _CREDS_FILE.exists():
        try:
            creds = json.loads(_CREDS_FILE.read_text())
            creds.pop("_comment", None)
            return creds
        except Exception:
            pass
    return {}


def get_telegram_config() -> Tuple[str, str]:
    """Return (bot_token, chat_id); either may be empty if unconfigured."""
    creds = _load_credentials()
    token = os.getenv("TELEGRAM_BOT_TOKEN") or creds.get("telegram_bot_token", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or creds.get("telegram_chat_id", "")
    return token, chat_id


def is_telegram_configured() -> bool:
    token, chat_id = get_telegram_config()
    return bool(token and chat_id)


def is_desktop_available() -> bool:
    """macOS desktop notifications need osascript."""
    return platform.system() == "Darwin" and shutil.which("osascript") is not None


def channel_status() -> Dict[str, bool]:
    """Which delivery channels are currently usable."""
    return {
        "in_app": True,  # always available
        "telegram": is_telegram_configured(),
        "desktop": is_desktop_available(),
    }


# ── Message formatting ────────────────────────────────────────────────────────

def format_event_text(event_dict: Dict) -> Tuple[str, str]:
    """Return (title_line, body_text) for an event dict (from MarketEvent.to_dict)."""
    sev = event_dict.get("severity", "medium")
    etype = event_dict.get("event_type", "news")
    sym = event_dict.get("symbol")
    icon = EVENT_EMOJI.get(etype, "•")
    sev_icon = SEVERITY_EMOJI.get(sev, "")

    title = event_dict.get("title", "(no title)")
    head = f"{sev_icon}{icon} {title}"

    lines: List[str] = []
    if sym:
        lines.append(f"Symbol: {sym}")
    lines.append(f"Type: {etype} · Severity: {sev}")
    if event_dict.get("body"):
        lines.append(str(event_dict["body"]))
    if event_dict.get("url"):
        lines.append(str(event_dict["url"]))
    return head, "\n".join(lines)


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(title: str, body: str,
                  token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
    """
    Send a Telegram message. Raises on failure (caller records the delivery).
    """
    if token is None or chat_id is None:
        token, chat_id = get_telegram_config()
    if not token or not chat_id:
        raise ValueError("Telegram not configured (missing bot token or chat id)")

    text = f"*{_escape_md(title)}*\n{body}" if body else f"*{_escape_md(title)}*"
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown",
              "disable_web_page_preview": True},
        timeout=_HTTP_TIMEOUT,
    )
    if resp.status_code != 200:
        # Telegram returns a JSON description we can surface for debugging.
        detail = ""
        try:
            detail = resp.json().get("description", "")
        except Exception:
            detail = resp.text[:200]
        raise RuntimeError(f"Telegram HTTP {resp.status_code}: {detail}")


def _escape_md(text: str) -> str:
    """Escape the Markdown chars that would break Telegram's parser in a title."""
    for ch in ("_", "*", "[", "]", "`"):
        text = text.replace(ch, " ")
    return text


# ── Desktop (macOS) ───────────────────────────────────────────────────────────

def send_desktop(title: str, body: str) -> None:
    """
    Show a macOS notification via osascript. Raises on failure.
    """
    if not is_desktop_available():
        raise RuntimeError("Desktop notifications unavailable (non-macOS or osascript missing)")

    # Sanitise quotes so they can't break out of the AppleScript string literals.
    safe_title = title.replace('"', "'").replace("\\", "")
    safe_body = body.replace('"', "'").replace("\\", "").replace("\n", " ")[:240]
    script = f'display notification "{safe_body}" with title "{safe_title}"'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed: {result.stderr.strip()[:200]}")


# ── Dispatch ──────────────────────────────────────────────────────────────────

def dispatch(event_dict: Dict, channels: List[str], repo,
             rule_id: Optional[str] = None) -> Dict[str, str]:
    """
    Deliver one event to the given channels, recording each attempt via ``repo``.

    Args:
        event_dict: serialised MarketEvent (must include 'id').
        channels:   list of 'in_app' | 'telegram' | 'desktop'.
        repo:       an EventRepository for recording AlertDelivery rows.
        rule_id:    the rule that triggered this, for the audit trail.

    Returns a {channel: status} map. Never raises.
    """
    event_id = event_dict.get("id", "")
    title, body = format_event_text(event_dict)
    results: Dict[str, str] = {}

    for channel in dict.fromkeys(channels):  # de-dupe, preserve order
        status, error = "sent", None
        try:
            if channel == "in_app":
                pass  # surfaced via /api/events; nothing to send
            elif channel == "telegram":
                if not is_telegram_configured():
                    status, error = "skipped", "Telegram not configured"
                else:
                    send_telegram(title, body)
            elif channel == "desktop":
                if not is_desktop_available():
                    status, error = "skipped", "Desktop notifications unavailable"
                else:
                    send_desktop(title, body)
            else:
                status, error = "skipped", f"Unknown channel: {channel}"
        except Exception as exc:
            status, error = "failed", str(exc)[:300]
            logger.warning("Notification via %s failed: %s", channel, exc)

        results[channel] = status
        if repo is not None and event_id:
            try:
                repo.record_delivery(
                    market_event_id=event_id, channel=channel,
                    status=status, rule_id=rule_id, error=error,
                )
            except Exception as exc:
                logger.error("Failed to record delivery for %s: %s", channel, exc)

    return results
