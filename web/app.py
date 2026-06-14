"""
Flask web dashboard for cash-secured put scan results.

Follows dev-patterns:
- Configuration loaded from environment variables
- Error handling with user-friendly messages
- Database initialization and migrations
- Blueprints for route organization
"""

from __future__ import annotations

import sys
import threading
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from flask import Flask, jsonify, render_template, request, make_response

# Ensure project root is on sys.path when running as `python -m web.app`
PROJECT_ROOT = __import__("os").path.abspath(__import__("os").path.join(__import__("os").path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from options_scanner import OptionsScanner
from web.results_loader import list_scans, load_latest_scan, load_scan
from web.alpaca_service import get_account, get_positions, get_orders, place_csp_order
from web.config import get_config
from web.database import DatabaseManager, init_db
from web.routes.trades import trades_bp
from web.routes.alerts import alerts_bp
from web.services import event_monitor
from scanner.strategy_registry import get_all_strategies

# Configure logging (must precede any logger use below)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Import strategies module to trigger strategy registration
try:
    import scanner.strategies  # noqa: F401
except ImportError as e:
    logger.warning(f"Could not import strategies module: {e}")

# Load configuration
try:
    config = get_config()
    logger.info(f"Configuration loaded: {config}")
except ValueError as e:
    logger.error(f"Configuration error: {str(e)}")
    raise

# Create Flask app
app = Flask(__name__)

# Apply configuration
app.config["HOST"] = config.HOST
app.config["PORT"] = config.PORT
app.config["DEBUG"] = config.DEBUG
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = config.SEND_FILE_MAX_AGE_DEFAULT
app.config["TEMPLATES_AUTO_RELOAD"] = config.TEMPLATES_AUTO_RELOAD
app.config["JSON_SORT_KEYS"] = config.JSON_SORT_KEYS

# Initialize database
try:
    init_db()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.error(f"Database initialization failed: {str(e)}")
    # Continue anyway - scanner routes don't need database yet

# Register blueprints
app.register_blueprint(trades_bp)
logger.info("Registered trade routes blueprint")
app.register_blueprint(alerts_bp)
logger.info("Registered alerts routes blueprint")

# Start the market-event monitor in the background. No-ops quietly if no event
# sources are configured yet (it can be started later via /api/monitor/status).
try:
    if event_monitor.start_monitor():
        logger.info("Event monitor started")
except Exception as exc:
    logger.warning(f"Could not start event monitor: {exc}")

_scan_lock = threading.Lock()
_scan_state: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "latest_timestamp": None,
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


DTE_PRESETS = {
    "WEEKLY":    (1,   7),
    "MONTHLY":   (21,  35),
    "STANDARD":  (38,  52),
    "QUARTERLY": (60,  90),
    "LEAPS":     (180, 730),
}


def _run_scan_background(dte_min: int, dte_max: int) -> None:
    global _scan_state
    try:
        scanner = OptionsScanner()
        scanner.run_scan(dte_min=dte_min, dte_max=dte_max)
        scans = list_scans()
        latest_ts = scans[0]["timestamp"] if scans else None
        with _scan_lock:
            _scan_state["running"] = False
            _scan_state["finished_at"] = _iso_now()
            _scan_state["error"] = None
            _scan_state["latest_timestamp"] = latest_ts
    except Exception as exc:
        with _scan_lock:
            _scan_state["running"] = False
            _scan_state["finished_at"] = _iso_now()
            _scan_state["error"] = str(exc)


@app.route("/")
def home():
    """Home page with strategy selection."""
    return render_template("home.html")


@app.route("/scanner")
def scanner():
    """Scanner page - accepts ?strategy=CSP parameter."""
    return render_template("index.html")


@app.route("/alerts")
def alerts_page():
    """Market-event monitoring & alerts page."""
    return render_template("alerts.html")


@app.route("/api/strategies")
def api_strategies():
    """Return list of available strategies for home screen."""
    try:
        strategies = get_all_strategies()
        return jsonify({
            "strategies": [metadata.to_dict() for metadata in strategies.values()]
        }), 200
    except Exception as e:
        logger.error(f"Error fetching strategies: {str(e)}")
        return jsonify({"error": "Failed to fetch strategies"}), 500


@app.route("/api/scans")
def api_scans():
    scans = list_scans()
    return jsonify([{"timestamp": s["timestamp"], "scan_time": s["scan_time"]} for s in scans])


@app.route("/api/results/latest")
def api_results_latest():
    try:
        return jsonify(load_latest_scan())
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404


@app.route("/api/results/<timestamp>")
def api_results_timestamp(timestamp: str):
    try:
        return jsonify(load_scan(timestamp))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404


@app.route("/api/presets")
def api_presets():
    return jsonify([
        {"name": k, "dte_min": v[0], "dte_max": v[1]}
        for k, v in DTE_PRESETS.items()
    ])


@app.route("/api/scan", methods=["POST"])
def api_scan_start():
    body = request.get_json(silent=True) or {}

    # Get strategy (default to CSP for backward compatibility)
    strategy = str(body.get("strategy", "CSP")).upper()
    logger.info(f"Scan request for strategy: {strategy}")

    # Resolve preset name → dte_min/dte_max
    preset = str(body.get("preset", "")).upper()
    if preset in DTE_PRESETS:
        default_min, default_max = DTE_PRESETS[preset]
    else:
        default_min, default_max = 1, 730

    dte_min = int(body.get("dte_min", default_min))
    dte_max = int(body.get("dte_max", default_max))

    with _scan_lock:
        if _scan_state["running"]:
            return jsonify({"error": "Scan already in progress"}), 409
        _scan_state["running"] = True
        _scan_state["started_at"] = _iso_now()
        _scan_state["finished_at"] = None
        _scan_state["error"] = None
        _scan_state["latest_timestamp"] = None
        _scan_state["dte_min"] = dte_min
        _scan_state["dte_max"] = dte_max
        _scan_state["strategy"] = strategy

    # For now, still use OptionsScanner (CSP-only) for backward compatibility
    # TODO: In Phase 2, use strategy registry to dispatch to appropriate strategy
    thread = threading.Thread(target=_run_scan_background, args=(dte_min, dte_max), daemon=True)
    thread.start()
    return jsonify({"status": "started", "dte_min": dte_min, "dte_max": dte_max, "strategy": strategy}), 202


@app.route("/api/scan/status")
def api_scan_status():
    with _scan_lock:
        return jsonify(dict(_scan_state))


# ---------------------------------------------------------------------------
# Alpaca paper trading routes
# Credentials are passed per-request via X-APCA-Key / X-APCA-Secret headers.
# The server never stores or logs them.
# ---------------------------------------------------------------------------

def _alpaca_creds():
    """Extract Alpaca credentials from request headers. Returns (key, secret) or raises."""
    key = request.headers.get("X-APCA-Key", "").strip()
    secret = request.headers.get("X-APCA-Secret", "").strip()
    if not key or not secret:
        raise ValueError("Missing Alpaca credentials in request headers")
    return key, secret


@app.route("/api/alpaca/account")
def api_alpaca_account():
    try:
        key, secret = _alpaca_creds()
        return jsonify(get_account(key, secret))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/alpaca/positions")
def api_alpaca_positions():
    try:
        key, secret = _alpaca_creds()
        return jsonify(get_positions(key, secret))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/alpaca/orders")
def api_alpaca_orders():
    try:
        key, secret = _alpaca_creds()
        limit = min(int(request.args.get("limit", 20)), 100)
        return jsonify(get_orders(key, secret, limit=limit))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/alpaca/order", methods=["POST"])
def api_alpaca_order():
    try:
        key, secret = _alpaca_creds()
        body = request.get_json(silent=True) or {}
        symbol = str(body.get("symbol", "")).upper().strip()
        expiration = str(body.get("expiration", "")).strip()
        strike = float(body.get("strike", 0))
        limit_price = float(body.get("limit_price", 0))
        qty = int(body.get("qty", 1))
        if not symbol or not expiration or strike <= 0 or limit_price <= 0:
            return jsonify({"error": "Missing or invalid order fields"}), 400
        result = place_csp_order(key, secret, symbol, expiration, strike, limit_price, qty)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


# ---------------------------------------------------------------------------
# Data provider status + credential management
# ---------------------------------------------------------------------------

@app.route("/api/providers")
def api_providers():
    """Return status of configured data providers."""
    from scanner.data_providers import is_tradier_configured, is_alpaca_configured
    return jsonify({
        "tradier": is_tradier_configured(),
        "alpaca_data": is_alpaca_configured(),
    })


@app.route("/api/providers/credentials", methods=["POST"])
def api_save_credentials():
    """
    Save Tradier/Alpaca credentials to data/credentials.json.
    Body: { tradier_token, tradier_sandbox, alpaca_key, alpaca_secret }
    Only non-empty values overwrite existing ones.
    """
    import json
    from pathlib import Path
    creds_path = Path(__file__).parent.parent / "data" / "credentials.json"
    body = request.get_json(silent=True) or {}

    # Load existing (strip the _comment key)
    existing = {}
    if creds_path.exists():
        try:
            existing = json.loads(creds_path.read_text())
            existing.pop("_comment", None)
        except Exception:
            pass

    updatable = [
        "tradier_token", "tradier_sandbox", "alpaca_key", "alpaca_secret",
        # Market-event monitoring + alerting
        "finnhub_token", "political_feed_url",
        "telegram_bot_token", "telegram_chat_id",
        "poll_interval_seconds", "price_move_pct", "volume_multiple",
        "news_max_age_minutes",
    ]
    for k in updatable:
        if k in body and body[k] != "" and body[k] is not None:
            existing[k] = body[k]

    creds_path.parent.mkdir(parents=True, exist_ok=True)
    creds_path.write_text(json.dumps(existing, indent=2))

    # Reset singletons so next scan picks up new creds
    import scanner.data_providers as dp
    dp._tradier_client = None
    dp._alpaca_client  = None

    from scanner.data_providers import is_tradier_configured, is_alpaca_configured
    return jsonify({
        "saved": True,
        "tradier": is_tradier_configured(),
        "alpaca_data": is_alpaca_configured(),
    })


def create_app() -> Flask:
    return app


def main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Run the scan results dashboard")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "5000")))
    parser.add_argument("--debug", action="store_true", default=os.getenv("DEBUG", "").lower() == "true")
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
