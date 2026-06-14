"""
Trade journal API routes.

Follows dev-patterns error handling:
- All endpoints wrapped in try-except
- User-friendly error messages (never raw exceptions)
- Proper HTTP status codes (400, 404, 500)
- Comprehensive request validation

Reference: .claude/referenced-skills/dev-patterns/error-handling/
"""

import logging
from flask import Blueprint, request, jsonify
from sqlalchemy.orm import Session
from datetime import datetime

from web.models.trade import Trade, TradeValidationError
from web.services.performance_service import PerformanceService
from web.database import get_db_session
from web.repositories.trade_repository import TradeRepository
from web.alpaca_service import get_closed_orders

logger = logging.getLogger(__name__)

trades_bp = Blueprint('trades', __name__, url_prefix='/api/trades')


# =========================================================================
# Error Response Helpers
# =========================================================================

def error_response(message: str, status_code: int = 400, details: dict = None) -> tuple:
    """
    Create a consistent error response.

    Args:
        message: User-friendly error message
        status_code: HTTP status code
        details: Optional additional error details

    Returns:
        Tuple of (JSON response, status_code)
    """
    response = {"error": message}
    if details:
        response["details"] = details
    return jsonify(response), status_code


def success_response(data: dict, status_code: int = 200) -> tuple:
    """
    Create a consistent success response.

    Args:
        data: Response data
        status_code: HTTP status code

    Returns:
        Tuple of (JSON response, status_code)
    """
    return jsonify(data), status_code


# =========================================================================
# GET /api/trades - List all trades
# =========================================================================

@trades_bp.route('', methods=['GET'])
def list_trades():
    """
    List all trades with optional filters.

    Query Parameters:
        - symbol: Filter by symbol (e.g., ?symbol=AAPL)
        - status: Filter by status (open/closed)
        - start_date: Filter by start date (YYYY-MM-DD)
        - end_date: Filter by end date (YYYY-MM-DD)
        - limit: Limit number of results (default: 100, max: 1000)
        - offset: Offset for pagination (default: 0)

    Returns:
        JSON list of trades
    """
    db = None
    try:
        # Get optional filters from query parameters
        symbol = request.args.get('symbol', '').upper().strip()
        status = request.args.get('status', '').lower().strip()
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')

        # Validate pagination parameters
        try:
            limit = int(request.args.get('limit', 100))
            offset = int(request.args.get('offset', 0))
            if limit < 1 or limit > 1000:
                return error_response("Limit must be between 1 and 1000", 400)
            if offset < 0:
                return error_response("Offset must be non-negative", 400)
        except ValueError:
            return error_response("Limit and offset must be integers", 400)

        # Validate filters
        if symbol:
            if not symbol.isalpha() or len(symbol) > 5:
                return error_response("Invalid symbol format", 400)

        if status:
            if status not in ('open', 'closed'):
                return error_response("Status must be 'open' or 'closed'", 400)

        if start_date:
            try:
                datetime.strptime(start_date, '%Y-%m-%d')
            except ValueError:
                return error_response("start_date must be YYYY-MM-DD format", 400)

        if end_date:
            try:
                datetime.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                return error_response("end_date must be YYYY-MM-DD format", 400)

        # Query database
        db = get_db_session()
        repo = TradeRepository(db)
        trades, total = repo.list_all(
            symbol=symbol if symbol else None,
            status=status if status else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            limit=limit,
            offset=offset,
        )

        logger.info(f"Listed trades: {len(trades)} results (total: {total})")

        return success_response({
            "trades": [t.to_dict() for t in trades],
            "count": len(trades),
            "total": total,
            "limit": limit,
            "offset": offset,
        })

    except Exception as e:
        logger.error(f"Error listing trades: {str(e)}", exc_info=True)
        return error_response("Failed to list trades", 500)
    finally:
        if db:
            db.close()


# =========================================================================
# POST /api/trades - Create new trade
# =========================================================================

@trades_bp.route('', methods=['POST'])
def create_trade():
    """
    Create a new trade journal entry.

    Request Body (JSON):
        {
            "symbol": "AAPL",
            "strike": 185.0,
            "expiration": "2026-07-24",
            "dte_at_entry": 45,
            "premium_received": 3.40,
            "contracts": 1,
            "capital_required": 18500.00,
            "delta_at_entry": -0.176,
            "realistic_yield_at_entry": 12.79,
            "entry_notes": "Optional notes",
            "entry_tech_score": 54,
            "entry_pivot_daily": 208.1,
            "entry_pivot_weekly": 213.81
        }

    Returns:
        JSON trade object with id and timestamps
    """
    db = None
    try:
        # Get JSON request body
        data = request.get_json(silent=True)
        if not data:
            return error_response("Request body must be valid JSON", 400)

        # Validate request has required fields
        required_fields = [
            'symbol', 'strike', 'expiration', 'dte_at_entry',
            'premium_received', 'contracts', 'capital_required',
            'delta_at_entry', 'realistic_yield_at_entry'
        ]
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            return error_response(
                f"Missing required fields: {', '.join(missing_fields)}",
                400,
                {"missing_fields": missing_fields}
            )

        # Attempt to create trade with validation and save to database
        try:
            db = get_db_session()
            repo = TradeRepository(db)
            trade = repo.create(data)
            logger.info(f"Created trade: {trade.id} ({trade.symbol} ${trade.strike})")
            return success_response(trade.to_dict(), status_code=201)
        except TradeValidationError as e:
            logger.warning(f"Trade validation failed: {str(e)}")
            return error_response(
                f"Invalid trade data: {str(e)}",
                400,
                {"validation_error": str(e)}
            )

    except Exception as e:
        logger.error(f"Error creating trade: {str(e)}", exc_info=True)
        return error_response("Failed to create trade", 500)
    finally:
        if db:
            db.close()


# =========================================================================
# GET /api/trades/{id} - Get single trade
# =========================================================================

@trades_bp.route('/<trade_id>', methods=['GET'])
def get_trade(trade_id: str):
    """
    Get a single trade by ID.

    Args:
        trade_id: Trade UUID

    Returns:
        JSON trade object
    """
    db = None
    try:
        # Validate trade_id format (UUID)
        if not trade_id or len(trade_id) != 36:  # UUID4 is 36 chars
            return error_response("Invalid trade ID format", 400)

        # Query database
        db = get_db_session()
        repo = TradeRepository(db)
        trade = repo.get_by_id(trade_id)

        if not trade:
            return error_response(f"Trade {trade_id} not found", 404)

        logger.info(f"Retrieved trade: {trade_id}")
        return success_response(trade.to_dict())

    except Exception as e:
        logger.error(f"Error retrieving trade {trade_id}: {str(e)}", exc_info=True)
        return error_response("Failed to retrieve trade", 500)
    finally:
        if db:
            db.close()


# =========================================================================
# PUT /api/trades/{id} - Update trade
# =========================================================================

@trades_bp.route('/<trade_id>', methods=['PUT'])
def update_trade(trade_id: str):
    """
    Update a trade (typically to close it).

    Args:
        trade_id: Trade UUID

    Request Body (JSON):
        {
            "exit_type": "expiration",  # or "assignment", "bought_back", "manual_close"
            "buy_back_price": 2.90,
            "close_price": 0.10,
            "exit_notes": "Expired worthless"
        }

    Returns:
        JSON updated trade object
    """
    db = None
    try:
        # Validate trade_id format
        if not trade_id or len(trade_id) != 36:
            return error_response("Invalid trade ID format", 400)

        # Get JSON request body
        data = request.get_json(silent=True)
        if not data:
            return error_response("Request body must be valid JSON", 400)

        # Validate exit_type if provided
        if 'exit_type' in data:
            valid_types = {'expiration', 'assignment', 'bought_back', 'manual_close'}
            if data['exit_type'] not in valid_types:
                return error_response(
                    f"Invalid exit_type. Must be one of: {', '.join(valid_types)}",
                    400
                )

        # Update trade in database
        try:
            db = get_db_session()
            repo = TradeRepository(db)
            trade = repo.update(trade_id, data)

            if not trade:
                return error_response(f"Trade {trade_id} not found", 404)

            logger.info(f"Updated trade: {trade_id}")
            return success_response(trade.to_dict())
        except TradeValidationError as e:
            logger.warning(f"Trade update validation failed: {str(e)}")
            return error_response(
                f"Invalid trade data: {str(e)}",
                400,
                {"validation_error": str(e)}
            )

    except Exception as e:
        logger.error(f"Error updating trade {trade_id}: {str(e)}", exc_info=True)
        return error_response("Failed to update trade", 500)
    finally:
        if db:
            db.close()


# =========================================================================
# POST /api/trades/sync-alpaca - Sync with Alpaca
# =========================================================================

@trades_bp.route('/sync-alpaca', methods=['POST'])
def sync_alpaca_positions():
    """
    Synchronize closed positions from Alpaca with trade journal.

    Requires Alpaca credentials via headers:
        - X-APCA-Key: API key
        - X-APCA-Secret: API secret

    Query Parameters:
        - days_back: Number of days to look back (default: 90, max: 365)

    Returns:
        JSON result with synced trade count
    """
    db = None
    try:
        # Get Alpaca credentials from headers
        key = request.headers.get('X-APCA-Key', '').strip()
        secret = request.headers.get('X-APCA-Secret', '').strip()

        if not key or not secret:
            return error_response("Missing Alpaca credentials in headers", 400)

        # Get optional days_back parameter
        try:
            days_back = int(request.args.get('days_back', 90))
            if days_back < 1 or days_back > 365:
                return error_response(
                    "days_back must be between 1 and 365",
                    400
                )
        except ValueError:
            return error_response("days_back must be an integer", 400)

        # Fetch closed orders from Alpaca
        closed_orders = get_closed_orders(key, secret, days_back)

        if not closed_orders:
            return success_response({
                "synced": 0,
                "created": 0,
                "updated": 0,
                "message": "No closed orders found in the specified period"
            })

        # Get database connection
        db = get_db_session()
        repo = TradeRepository(db)

        synced = 0
        created = 0
        updated = 0
        errors = []

        # Process each closed order
        for order in closed_orders:
            try:
                # Parse option symbol: AAPL260815P00280000
                # Format: [SYMBOL][YYMMDD][P/C][STRIKE]
                symbol_str = order['symbol']

                # Extract underlying symbol (letters at start)
                underlying = ''.join(c for c in symbol_str if c.isalpha() and c not in 'PC')

                # Extract expiration date (6 digits after symbol)
                exp_start = len(underlying)
                exp_digits = symbol_str[exp_start:exp_start+6]
                if len(exp_digits) == 6:
                    # Convert YYMMDD to YYYY-MM-DD
                    yy = int(exp_digits[0:2])
                    mm = int(exp_digits[2:4])
                    dd = int(exp_digits[4:6])
                    # Assume 2026 (current year from context)
                    expiration = f"20{yy}-{mm:02d}-{dd:02d}"
                else:
                    logger.warning(f"Could not parse expiration from {symbol_str}")
                    continue

                # Check if trade already exists
                existing_trades = repo.get_by_symbol(underlying)
                matching_trade = None

                for trade in existing_trades:
                    if (trade.expiration == expiration and
                        trade.status == 'closed' and
                        trade.buy_back_price is not None):
                        matching_trade = trade
                        break

                # Extract strike (last 8 digits)
                strike_str = symbol_str[-8:]
                strike = int(strike_str) / 1000.0

                if matching_trade:
                    # Update existing trade with filled price
                    update_data = {
                        'exit_type': 'expiration',
                        'buy_back_price': float(order['filled_avg_price']) if order['filled_avg_price'] else 0,
                        'exit_date': order['filled_at'],
                    }
                    repo.update(matching_trade.id, update_data)
                    updated += 1
                    logger.info(f"Updated trade: {underlying} {expiration} ${strike}")
                else:
                    # Create new trade from filled order
                    trade_data = {
                        'symbol': underlying,
                        'strike': strike,
                        'expiration': expiration,
                        'dte_at_entry': 0,  # Will be calculated
                        'premium_received': float(order['limit_price']) if order['limit_price'] else 0,
                        'contracts': int(order['qty']) if order['qty'] else 1,
                        'capital_required': strike * 100 * (int(order['qty']) if order['qty'] else 1),
                        'delta_at_entry': -0.15,  # Estimate
                        'realistic_yield_at_entry': 0,
                        'entry_notes': f'Synced from Alpaca order {order["id"]}',
                        'entry_tech_score': None,
                        'entry_pivot_daily': None,
                        'entry_pivot_weekly': None,
                    }

                    try:
                        trade = repo.create(trade_data)
                        # Close the trade with filled price
                        close_data = {
                            'exit_type': 'expiration',
                            'buy_back_price': float(order['filled_avg_price']) if order['filled_avg_price'] else 0,
                            'exit_date': order['filled_at'],
                            'exit_notes': f'Synced from Alpaca order {order["id"]}',
                        }
                        repo.update(trade.id, close_data)
                        created += 1
                        logger.info(f"Created trade: {underlying} {expiration} ${strike}")
                    except TradeValidationError as e:
                        logger.warning(f"Could not create trade for {underlying}: {str(e)}")
                        errors.append(f"{underlying}: {str(e)}")

                synced += 1

            except Exception as e:
                logger.error(f"Error processing order {order.get('id')}: {str(e)}")
                errors.append(f"Order {order.get('id')}: {str(e)}")
                continue

        logger.info(f"Sync completed: {synced} orders processed, {created} created, {updated} updated")

        return success_response({
            "synced": synced,
            "created": created,
            "updated": updated,
            "errors": errors if errors else None,
            "message": f"Sync completed: {created} trades created, {updated} updated"
        })

    except Exception as e:
        logger.error(f"Error syncing Alpaca positions: {str(e)}", exc_info=True)
        return error_response("Failed to sync with Alpaca", 500)
    finally:
        if db:
            db.close()


# =========================================================================
# GET /api/performance - Aggregate performance metrics
# =========================================================================

@trades_bp.route('/performance', methods=['GET'])
def get_performance():
    """
    Get aggregate performance metrics across all trades.

    Returns:
        JSON object with:
        - total_trades
        - win_rate_pct
        - average_roi_pct
        - total_realized_pnl
        - sharpe_ratio
        - max_drawdown_pct
    """
    db = None
    try:
        # Query all trades from database
        db = get_db_session()
        repo = TradeRepository(db)
        trades = repo.get_all()

        if not trades:
            return success_response({
                "message": "No trades found",
                "metrics": {}
            })

        # Convert to dict for PerformanceService
        trade_dicts = [t.to_dict() for t in trades]

        # Calculate performance metrics
        metrics = PerformanceService.get_aggregate_performance(trade_dicts)

        logger.info(f"Calculated performance: {metrics['win_rate_pct']}% win rate")

        return success_response({"metrics": metrics})

    except Exception as e:
        logger.error(f"Error calculating performance: {str(e)}", exc_info=True)
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return error_response(f"Failed to calculate performance: {str(e)}", 500)
    finally:
        if db:
            db.close()


# =========================================================================
# GET /api/performance/monthly - Monthly breakdown
# =========================================================================

@trades_bp.route('/performance/monthly', methods=['GET'])
def get_monthly_performance():
    """
    Get monthly performance breakdown.

    Returns:
        JSON object with metrics per month (YYYY-MM format)
    """
    db = None
    try:
        # Query all trades from database
        db = get_db_session()
        repo = TradeRepository(db)
        trades = repo.get_all()

        if not trades:
            return success_response({
                "message": "No trades found",
                "monthly": {}
            })

        # Convert to dict for PerformanceService
        trade_dicts = [t.to_dict() for t in trades]

        # Calculate monthly metrics
        monthly = PerformanceService.get_monthly_performance(trade_dicts)

        logger.info(f"Calculated monthly performance: {len(monthly)} months")

        return success_response({"monthly": monthly})

    except Exception as e:
        logger.error(f"Error calculating monthly performance: {str(e)}", exc_info=True)
        return error_response("Failed to calculate monthly performance", 500)
    finally:
        if db:
            db.close()


# =========================================================================
# GET /api/performance/by-strategy - Strategy analysis
# =========================================================================

@trades_bp.route('/performance/by-strategy', methods=['GET'])
def get_strategy_performance():
    """
    Get performance breakdown by trading strategy dimensions.

    Query Parameters:
        - breakdown: Type of breakdown (delta_band, dte_window, symbol)

    Returns:
        JSON object with strategy analysis
    """
    db = None
    try:
        breakdown = request.args.get('breakdown', 'delta_band').lower().strip()

        valid_breakdowns = {'delta_band', 'dte_window', 'symbol'}
        if breakdown not in valid_breakdowns:
            return error_response(
                f"Invalid breakdown. Must be one of: {', '.join(valid_breakdowns)}",
                400
            )

        # Query all trades from database
        db = get_db_session()
        repo = TradeRepository(db)
        trades = repo.get_all()

        if not trades:
            return success_response({
                "message": "No trades found",
                "breakdown": breakdown,
                "analysis": {}
            })

        # Convert to dict for PerformanceService
        trade_dicts = [t.to_dict() for t in trades]

        # Calculate strategy metrics based on breakdown type
        if breakdown == 'delta_band':
            analysis = PerformanceService.analyze_by_delta_band(trade_dicts)
        elif breakdown == 'dte_window':
            analysis = PerformanceService.analyze_by_dte_window(trade_dicts)
        elif breakdown == 'symbol':
            analysis = PerformanceService.analyze_by_symbol(trade_dicts)

        logger.info(f"Calculated strategy performance: {breakdown}")

        return success_response({
            "breakdown": breakdown,
            "analysis": analysis
        })

    except Exception as e:
        logger.error(f"Error calculating strategy performance: {str(e)}", exc_info=True)
        return error_response("Failed to calculate strategy performance", 500)
    finally:
        if db:
            db.close()
