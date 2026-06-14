"""
Alerts / market-event monitoring API routes.

Follows the same conventions as trades.py: blueprint, try/except per handler,
``error_response``/``success_response`` helpers, session opened then closed in
``finally``.

Endpoints (all under /api):
  GET    /api/events                 recent events (dashboard polling)
  POST   /api/events/<id>/seen       mark an event read
  GET    /api/alert-rules            list rules
  POST   /api/alert-rules            create a rule
  PUT    /api/alert-rules/<id>       update a rule
  DELETE /api/alert-rules/<id>       delete a rule
  GET    /api/monitor/status         monitor heartbeat + provider/channel status
  POST   /api/monitor/test           fire a synthetic alert through chosen channels
"""

import logging
from flask import Blueprint, request, jsonify

from web.database import get_db_session
from web.repositories.event_repository import EventRepository
from web.services import event_monitor
from web.models.market_event import CHANNELS

logger = logging.getLogger(__name__)

alerts_bp = Blueprint("alerts", __name__, url_prefix="/api")


def error_response(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def success_response(data, status_code: int = 200):
    return jsonify(data), status_code


# ── Events ────────────────────────────────────────────────────────────────────

@alerts_bp.route("/events")
def list_events():
    """Recent market events, newest first. ?limit, ?type, ?unseen=1"""
    db = None
    try:
        try:
            limit = int(request.args.get("limit", 100))
            limit = max(1, min(limit, 500))
        except ValueError:
            return error_response("limit must be an integer", 400)

        event_type = request.args.get("type", "").strip() or None
        unseen_only = request.args.get("unseen", "").lower() in ("1", "true", "yes")

        db = get_db_session()
        repo = EventRepository(db)
        events = repo.list_events(limit=limit, event_type=event_type, unseen_only=unseen_only)
        return success_response({
            "events": [e.to_dict() for e in events],
            "count": len(events),
        })
    except Exception as e:
        logger.error(f"list_events error: {e}")
        return error_response("Failed to load events", 500)
    finally:
        if db:
            db.close()


@alerts_bp.route("/events/<event_id>/seen", methods=["POST"])
def mark_event_seen(event_id: str):
    db = None
    try:
        db = get_db_session()
        repo = EventRepository(db)
        if repo.mark_seen(event_id):
            return success_response({"id": event_id, "seen": True})
        return error_response("Event not found", 404)
    except Exception as e:
        logger.error(f"mark_event_seen error: {e}")
        return error_response("Failed to update event", 500)
    finally:
        if db:
            db.close()


# ── Alert rules ───────────────────────────────────────────────────────────────

@alerts_bp.route("/alert-rules")
def list_rules():
    db = None
    try:
        db = get_db_session()
        repo = EventRepository(db)
        rules = repo.list_rules()
        return success_response({"rules": [r.to_dict() for r in rules]})
    except Exception as e:
        logger.error(f"list_rules error: {e}")
        return error_response("Failed to load rules", 500)
    finally:
        if db:
            db.close()


@alerts_bp.route("/alert-rules", methods=["POST"])
def create_rule():
    db = None
    try:
        body = request.get_json(silent=True) or {}
        if not str(body.get("name", "")).strip():
            return error_response("Rule name is required", 400)

        db = get_db_session()
        repo = EventRepository(db)
        rule = repo.create_rule(body)
        if rule is None:
            return error_response("Failed to create rule", 500)
        return success_response({"rule": rule.to_dict()}, 201)
    except Exception as e:
        logger.error(f"create_rule error: {e}")
        return error_response("Failed to create rule", 500)
    finally:
        if db:
            db.close()


@alerts_bp.route("/alert-rules/<rule_id>", methods=["PUT"])
def update_rule(rule_id: str):
    db = None
    try:
        body = request.get_json(silent=True) or {}
        db = get_db_session()
        repo = EventRepository(db)
        rule = repo.update_rule(rule_id, body)
        if rule is None:
            return error_response("Rule not found", 404)
        return success_response({"rule": rule.to_dict()})
    except Exception as e:
        logger.error(f"update_rule error: {e}")
        return error_response("Failed to update rule", 500)
    finally:
        if db:
            db.close()


@alerts_bp.route("/alert-rules/<rule_id>", methods=["DELETE"])
def delete_rule(rule_id: str):
    db = None
    try:
        db = get_db_session()
        repo = EventRepository(db)
        if repo.delete_rule(rule_id):
            return success_response({"deleted": rule_id})
        return error_response("Rule not found", 404)
    except Exception as e:
        logger.error(f"delete_rule error: {e}")
        return error_response("Failed to delete rule", 500)
    finally:
        if db:
            db.close()


# ── Monitor ───────────────────────────────────────────────────────────────────

@alerts_bp.route("/monitor/status")
def monitor_status():
    try:
        # Lazily start the monitor if creds were added after app boot.
        state = event_monitor.get_state()
        if not state.get("running") and any(state.get("providers", {}).values()):
            event_monitor.start_monitor()
            state = event_monitor.get_state()
        return success_response(state)
    except Exception as e:
        logger.error(f"monitor_status error: {e}")
        return error_response("Failed to get monitor status", 500)


@alerts_bp.route("/monitor/test", methods=["POST"])
def monitor_test():
    """Fire a synthetic alert through the requested channels (default: all)."""
    db = None
    try:
        body = request.get_json(silent=True) or {}
        channels = body.get("channels") or list(CHANNELS)
        channels = [c for c in channels if c in CHANNELS]
        if not channels:
            return error_response("No valid channels specified", 400)

        db = get_db_session()
        repo = EventRepository(db)
        result = event_monitor.run_test_alert(repo, channels)
        if "error" in result:
            return error_response(result["error"], 500)
        return success_response(result)
    except Exception as e:
        logger.error(f"monitor_test error: {e}")
        return error_response("Failed to send test alert", 500)
    finally:
        if db:
            db.close()
