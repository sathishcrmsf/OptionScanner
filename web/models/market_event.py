"""
Market-event monitoring models.

Three tables, all on the shared SQLAlchemy ``Base`` (defined in
``web.models.trade``) so they are auto-created by the same
``Base.metadata.create_all`` call in ``web/database.py``:

- ``MarketEvent``   — a detected market-moving event (calendar, news, unusual move, political).
- ``AlertRule``     — user-defined rule deciding which events alert, and on which channels.
- ``AlertDelivery`` — audit trail of each notification attempt.

Follows the existing model conventions (UUID string PKs, ``to_dict`` for JSON,
``utcnow`` defaults). JSON-list fields are stored as ``Text`` and (de)serialised
with helpers, matching the ``strategy_metadata`` approach already used by ``Trade``.
"""

import json
import uuid
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean

# Reuse the SAME declarative Base as Trade so all tables share one metadata
# registry and are created together by DatabaseManager.initialize().
from web.models.trade import Base

logger = logging.getLogger(__name__)


# Severity ordering, used for "min_severity" rule matching.
SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3}

# Recognised event types (informational; not enforced at the DB level).
EVENT_TYPES = {"economic", "news", "unusual_move", "political"}

# Recognised notification channels.
CHANNELS = {"in_app", "telegram", "desktop"}


def _dumps(value) -> str:
    """Serialise a list/dict to a JSON string for Text columns."""
    return json.dumps(value or [])


def _loads(raw: Optional[str]):
    """Deserialise a JSON Text column, tolerating None/garbage."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


class MarketEvent(Base):
    """A single detected market-moving event."""

    __tablename__ = "market_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Classification
    event_type = Column(String(20), nullable=False, index=True)  # economic|news|unusual_move|political
    source = Column(String(40), nullable=False)                  # finnhub|alpaca|political_feed|test
    symbol = Column(String(10), nullable=True, index=True)       # related ticker, if any
    severity = Column(String(10), nullable=False, default="medium")  # low|medium|high

    # Content
    title = Column(String(300), nullable=False)
    body = Column(Text, nullable=True)
    url = Column(String(500), nullable=True)

    # Deduplication: stable hash of (source + identifying content). Unique so the
    # same headline / calendar entry is only ever stored (and alerted) once.
    dedup_key = Column(String(64), nullable=False, unique=True, index=True)

    # State
    seen = Column(Boolean, nullable=False, default=False)
    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    @staticmethod
    def make_dedup_key(source: str, *parts: str) -> str:
        """Build a stable dedup hash from the source and identifying parts."""
        raw = "||".join([source, *[str(p) for p in parts]])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, data: Dict) -> "MarketEvent":
        """
        Build a MarketEvent from a provider dict.

        Expected keys: event_type, source, title; optional: symbol, severity,
        body, url, dedup_parts (list used to compute dedup_key), detected_at.
        """
        source = str(data.get("source", "unknown"))
        dedup_parts = data.get("dedup_parts") or [data.get("title", "")]
        dedup_key = cls.make_dedup_key(source, *dedup_parts)

        detected = data.get("detected_at")
        if isinstance(detected, str):
            try:
                detected = datetime.fromisoformat(detected)
            except Exception:
                detected = datetime.utcnow()
        elif not isinstance(detected, datetime):
            detected = datetime.utcnow()

        severity = str(data.get("severity", "medium")).lower()
        if severity not in SEVERITY_ORDER:
            severity = "medium"

        return cls(
            event_type=str(data.get("event_type", "news")),
            source=source,
            symbol=(str(data["symbol"]).upper() if data.get("symbol") else None),
            severity=severity,
            title=str(data.get("title", ""))[:300],
            body=data.get("body"),
            url=data.get("url"),
            dedup_key=dedup_key,
            detected_at=detected,
        )

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "source": self.source,
            "symbol": self.symbol,
            "severity": self.severity,
            "title": self.title,
            "body": self.body,
            "url": self.url,
            "seen": self.seen,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<MarketEvent {self.event_type}/{self.severity} {self.symbol or '-'} {self.title[:40]!r}>"


class AlertRule(Base):
    """A user-defined rule deciding which events fire alerts, and on which channels."""

    __tablename__ = "alert_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)

    # Matching criteria (empty list = "match anything" for that dimension)
    source_filter = Column(Text, nullable=False, default="[]")   # JSON list of event_types
    symbols = Column(Text, nullable=False, default="[]")         # JSON list of tickers
    keywords = Column(Text, nullable=False, default="[]")        # JSON list of substrings
    min_severity = Column(String(10), nullable=False, default="low")

    # Delivery
    channels = Column(Text, nullable=False, default='["in_app"]')  # JSON list of channels
    enabled = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- JSON accessors -----------------------------------------------------
    def get_source_filter(self) -> List[str]:
        return _loads(self.source_filter)

    def get_symbols(self) -> List[str]:
        return [s.upper() for s in _loads(self.symbols)]

    def get_keywords(self) -> List[str]:
        return [k.lower() for k in _loads(self.keywords)]

    def get_channels(self) -> List[str]:
        return _loads(self.channels) or ["in_app"]

    @classmethod
    def from_dict(cls, data: Dict) -> "AlertRule":
        """Build an AlertRule from API/form input."""
        min_sev = str(data.get("min_severity", "low")).lower()
        if min_sev not in SEVERITY_ORDER:
            min_sev = "low"
        channels = [c for c in (data.get("channels") or ["in_app"]) if c in CHANNELS] or ["in_app"]
        return cls(
            name=str(data.get("name", "Untitled rule"))[:100],
            source_filter=_dumps([s for s in (data.get("source_filter") or []) if s in EVENT_TYPES]),
            symbols=_dumps([str(s).upper() for s in (data.get("symbols") or [])]),
            keywords=_dumps([str(k) for k in (data.get("keywords") or [])]),
            min_severity=min_sev,
            channels=_dumps(channels),
            enabled=bool(data.get("enabled", True)),
        )

    def apply_update(self, data: Dict) -> None:
        """Apply a partial update from API input (only provided fields change)."""
        if "name" in data:
            self.name = str(data["name"])[:100]
        if "source_filter" in data:
            self.source_filter = _dumps([s for s in (data["source_filter"] or []) if s in EVENT_TYPES])
        if "symbols" in data:
            self.symbols = _dumps([str(s).upper() for s in (data["symbols"] or [])])
        if "keywords" in data:
            self.keywords = _dumps([str(k) for k in (data["keywords"] or [])])
        if "min_severity" in data:
            sev = str(data["min_severity"]).lower()
            if sev in SEVERITY_ORDER:
                self.min_severity = sev
        if "channels" in data:
            chans = [c for c in (data["channels"] or []) if c in CHANNELS] or ["in_app"]
            self.channels = _dumps(chans)
        if "enabled" in data:
            self.enabled = bool(data["enabled"])

    def matches(self, event: "MarketEvent") -> bool:
        """
        Decide whether this rule should alert on the given event.

        A rule matches when ALL specified criteria pass (unspecified = wildcard):
        - event_type is in source_filter (if set)
        - event severity >= min_severity
        - event symbol is in symbols (if set)
        - any keyword appears in the event title/body (if keywords set)
        """
        if not self.enabled:
            return False

        # Severity floor
        if SEVERITY_ORDER.get(event.severity, 0) < SEVERITY_ORDER.get(self.min_severity, 0):
            return False

        # Event-type filter
        sources = self.get_source_filter()
        if sources and event.event_type not in sources:
            return False

        # Symbol filter
        symbols = self.get_symbols()
        if symbols:
            if not event.symbol or event.symbol.upper() not in symbols:
                return False

        # Keyword filter
        keywords = self.get_keywords()
        if keywords:
            haystack = f"{event.title or ''} {event.body or ''}".lower()
            if not any(kw in haystack for kw in keywords):
                return False

        return True

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "source_filter": self.get_source_filter(),
            "symbols": self.get_symbols(),
            "keywords": _loads(self.keywords),
            "min_severity": self.min_severity,
            "channels": self.get_channels(),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<AlertRule {self.name!r} enabled={self.enabled}>"


class AlertDelivery(Base):
    """Audit trail: one row per notification attempt to one channel."""

    __tablename__ = "alert_deliveries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    market_event_id = Column(String(36), nullable=False, index=True)
    rule_id = Column(String(36), nullable=True)
    channel = Column(String(20), nullable=False)            # in_app|telegram|desktop
    status = Column(String(20), nullable=False, default="sent")  # sent|failed|skipped
    error = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "market_event_id": self.market_event_id,
            "rule_id": self.rule_id,
            "channel": self.channel,
            "status": self.status,
            "error": self.error,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }

    def __repr__(self) -> str:
        return f"<AlertDelivery {self.channel}/{self.status}>"
