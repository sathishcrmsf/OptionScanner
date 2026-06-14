"""
Trade data repository for database operations.

Follows dev-patterns:
- Separation of concerns (data access layer)
- Safe parameterized queries
- Error handling with logging
- Type hints and documentation

Reference: .claude/referenced-skills/dev-patterns/
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from web.models.trade import Trade, TradeValidationError

logger = logging.getLogger(__name__)


class TradeRepository:
    """Data access layer for trades."""

    def __init__(self, session: Session):
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    def create(self, data: Dict[str, Any]) -> Trade:
        """
        Create and save a new trade.

        Args:
            data: Trade data dictionary

        Returns:
            Created Trade instance

        Raises:
            TradeValidationError: If validation fails
            SQLAlchemyError: If database error occurs
        """
        try:
            trade = Trade.create_from_dict(data, self.session)
            self.session.commit()
            logger.info(f"Created trade: {trade.id} ({trade.symbol})")
            return trade
        except TradeValidationError:
            self.session.rollback()
            raise
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Database error creating trade: {str(e)}")
            raise ValueError(f"Failed to create trade: {str(e)}")

    def get_by_id(self, trade_id: str) -> Optional[Trade]:
        """
        Retrieve a trade by ID.

        Args:
            trade_id: Trade UUID

        Returns:
            Trade instance or None if not found
        """
        try:
            trade = self.session.query(Trade).filter(Trade.id == trade_id).first()
            return trade
        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving trade: {str(e)}")
            return None

    def list_all(
        self,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        strategy: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[Trade], int]:
        """
        List trades with optional filters.

        Args:
            symbol: Filter by symbol (e.g., "AAPL")
            status: Filter by status ("open" or "closed")
            strategy: Filter by strategy (e.g., "CSP", "WHEEL")
            start_date: Filter by start date (YYYY-MM-DD)
            end_date: Filter by end date (YYYY-MM-DD)
            limit: Max number of results
            offset: Pagination offset

        Returns:
            Tuple of (trades list, total count)
        """
        try:
            query = self.session.query(Trade)

            # Apply filters
            if symbol:
                query = query.filter(Trade.symbol == symbol.upper())
            if status:
                query = query.filter(Trade.status == status.lower())
            if strategy:
                query = query.filter(Trade.strategy == strategy.upper())
            if start_date:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Trade.entry_date >= start)
            if end_date:
                end = datetime.strptime(end_date, '%Y-%m-%d')
                query = query.filter(Trade.entry_date <= end)

            # Get total count
            total = query.count()

            # Apply pagination
            trades = query.order_by(Trade.entry_date.desc()).offset(offset).limit(limit).all()

            return trades, total

        except SQLAlchemyError as e:
            logger.error(f"Database error listing trades: {str(e)}")
            return [], 0

    def update(self, trade_id: str, data: Dict[str, Any]) -> Optional[Trade]:
        """
        Update a trade.

        Args:
            trade_id: Trade UUID
            data: Fields to update

        Returns:
            Updated Trade instance or None if not found
        """
        try:
            trade = self.get_by_id(trade_id)
            if not trade:
                return None

            # Handle closing a trade
            if 'exit_type' in data:
                try:
                    trade.close_trade(data)
                except TradeValidationError as e:
                    logger.warning(f"Trade close validation failed: {str(e)}")
                    raise
            else:
                # Update other fields
                for key, value in data.items():
                    if hasattr(trade, key) and key not in ['id', 'created_at']:
                        setattr(trade, key, value)

            trade.updated_at = datetime.utcnow()
            self.session.commit()
            logger.info(f"Updated trade: {trade.id}")
            return trade

        except TradeValidationError:
            self.session.rollback()
            raise
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Database error updating trade: {str(e)}")
            raise ValueError(f"Failed to update trade: {str(e)}")

    def delete(self, trade_id: str) -> bool:
        """
        Delete a trade (hard delete).

        Args:
            trade_id: Trade UUID

        Returns:
            True if deleted, False if not found
        """
        try:
            trade = self.get_by_id(trade_id)
            if not trade:
                return False

            self.session.delete(trade)
            self.session.commit()
            logger.info(f"Deleted trade: {trade_id}")
            return True

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Database error deleting trade: {str(e)}")
            raise ValueError(f"Failed to delete trade: {str(e)}")

    def get_all_closed(self) -> List[Trade]:
        """
        Get all closed trades (for performance analysis).

        Returns:
            List of closed trades ordered by entry date
        """
        try:
            trades = (
                self.session.query(Trade)
                .filter(Trade.status == 'closed')
                .order_by(Trade.entry_date.desc())
                .all()
            )
            return trades
        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving closed trades: {str(e)}")
            return []

    def get_all(self) -> List[Trade]:
        """
        Get all trades (for performance analysis).

        Returns:
            List of all trades ordered by entry date (newest first)
        """
        try:
            trades = (
                self.session.query(Trade)
                .order_by(Trade.entry_date.desc())
                .all()
            )
            return trades
        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving all trades: {str(e)}")
            return []

    def get_by_symbol(self, symbol: str) -> List[Trade]:
        """
        Get all trades for a symbol.

        Args:
            symbol: Stock ticker

        Returns:
            List of trades for that symbol
        """
        try:
            trades = (
                self.session.query(Trade)
                .filter(Trade.symbol == symbol.upper())
                .order_by(Trade.entry_date.desc())
                .all()
            )
            return trades
        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving trades for {symbol}: {str(e)}")
            return []

    def count_by_status(self) -> Dict[str, int]:
        """
        Get count of trades by status.

        Returns:
            Dict with open and closed counts
        """
        try:
            open_count = self.session.query(Trade).filter(Trade.status == 'open').count()
            closed_count = self.session.query(Trade).filter(Trade.status == 'closed').count()
            return {'open': open_count, 'closed': closed_count}
        except SQLAlchemyError as e:
            logger.error(f"Database error counting trades: {str(e)}")
            return {'open': 0, 'closed': 0}

    def close(self) -> None:
        """Close the database session."""
        try:
            self.session.close()
        except Exception as e:
            logger.error(f"Error closing session: {str(e)}")
