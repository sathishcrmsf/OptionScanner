"""
Data access layer for market events, alert rules, and deliveries.

Mirrors ``TradeRepository``: session injected, every method wrapped in
try/except with rollback on write failure and logging. Returns ORM objects
(callers serialise via ``to_dict``).
"""

import logging
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from web.models.market_event import MarketEvent, AlertRule, AlertDelivery

logger = logging.getLogger(__name__)


class EventRepository:
    """Data access for the market-event monitoring tables."""

    def __init__(self, session: Session):
        self.session = session

    # ── MarketEvent ────────────────────────────────────────────────────────

    def event_exists(self, dedup_key: str) -> bool:
        """True if an event with this dedup_key is already stored."""
        try:
            return (
                self.session.query(MarketEvent.id)
                .filter(MarketEvent.dedup_key == dedup_key)
                .first()
                is not None
            )
        except SQLAlchemyError as e:
            logger.error(f"event_exists query failed: {e}")
            return False

    def create_event(self, data: Dict[str, Any]) -> Optional[MarketEvent]:
        """
        Persist a new event from a provider dict. Returns the event, or None if
        it was a duplicate (dedup_key collision) or a DB error occurred.
        """
        event = MarketEvent.from_dict(data)
        try:
            self.session.add(event)
            self.session.commit()
            return event
        except IntegrityError:
            # Duplicate dedup_key — another tick already stored it. Not an error.
            self.session.rollback()
            return None
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"create_event failed: {e}")
            return None

    def list_events(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
        unseen_only: bool = False,
    ) -> List[MarketEvent]:
        """Recent events, newest first."""
        try:
            q = self.session.query(MarketEvent)
            if event_type:
                q = q.filter(MarketEvent.event_type == event_type)
            if unseen_only:
                q = q.filter(MarketEvent.seen.is_(False))
            return q.order_by(MarketEvent.detected_at.desc()).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"list_events failed: {e}")
            return []

    def get_event(self, event_id: str) -> Optional[MarketEvent]:
        try:
            return self.session.query(MarketEvent).filter(MarketEvent.id == event_id).first()
        except SQLAlchemyError as e:
            logger.error(f"get_event failed: {e}")
            return None

    def mark_seen(self, event_id: str) -> bool:
        try:
            ev = self.get_event(event_id)
            if not ev:
                return False
            ev.seen = True
            self.session.commit()
            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"mark_seen failed: {e}")
            return False

    def count_events_today(self) -> int:
        from datetime import datetime, time
        try:
            start = datetime.combine(datetime.utcnow().date(), time.min)
            return (
                self.session.query(MarketEvent)
                .filter(MarketEvent.detected_at >= start)
                .count()
            )
        except SQLAlchemyError as e:
            logger.error(f"count_events_today failed: {e}")
            return 0

    # ── AlertRule ──────────────────────────────────────────────────────────

    def list_rules(self, enabled_only: bool = False) -> List[AlertRule]:
        try:
            q = self.session.query(AlertRule)
            if enabled_only:
                q = q.filter(AlertRule.enabled.is_(True))
            return q.order_by(AlertRule.created_at.desc()).all()
        except SQLAlchemyError as e:
            logger.error(f"list_rules failed: {e}")
            return []

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        try:
            return self.session.query(AlertRule).filter(AlertRule.id == rule_id).first()
        except SQLAlchemyError as e:
            logger.error(f"get_rule failed: {e}")
            return None

    def create_rule(self, data: Dict[str, Any]) -> Optional[AlertRule]:
        rule = AlertRule.from_dict(data)
        try:
            self.session.add(rule)
            self.session.commit()
            logger.info(f"Created alert rule: {rule.id} ({rule.name})")
            return rule
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"create_rule failed: {e}")
            return None

    def update_rule(self, rule_id: str, data: Dict[str, Any]) -> Optional[AlertRule]:
        try:
            rule = self.get_rule(rule_id)
            if not rule:
                return None
            rule.apply_update(data)
            self.session.commit()
            return rule
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"update_rule failed: {e}")
            return None

    def delete_rule(self, rule_id: str) -> bool:
        try:
            rule = self.get_rule(rule_id)
            if not rule:
                return False
            self.session.delete(rule)
            self.session.commit()
            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"delete_rule failed: {e}")
            return False

    # ── AlertDelivery ──────────────────────────────────────────────────────

    def record_delivery(
        self,
        market_event_id: str,
        channel: str,
        status: str,
        rule_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[AlertDelivery]:
        delivery = AlertDelivery(
            market_event_id=market_event_id,
            rule_id=rule_id,
            channel=channel,
            status=status,
            error=error,
        )
        try:
            self.session.add(delivery)
            self.session.commit()
            return delivery
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"record_delivery failed: {e}")
            return None
