"""
Trade model for CSP (Cash-Secured Put) journal.

Follows data-quality-checker patterns: All fields validated before storage.
Uses SQLAlchemy ORM with proper type handling.

Reference: .claude/referenced-skills/data-quality-checker/scripts/validator.py
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from decimal import Decimal

from sqlalchemy import Column, String, Float, Integer, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

Base = declarative_base()


class TradeValidationError(ValueError):
    """Raised when trade data fails validation."""
    pass


class Trade(Base):
    """
    Cash-Secured Put trade journal entry.

    This model tracks all aspects of a CSP trade from entry to exit,
    including performance metrics for analysis.
    """

    __tablename__ = 'trades'

    # Primary Key
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Entry Information
    entry_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    symbol = Column(String(10), nullable=False, index=True)
    strike = Column(Float, nullable=False)  # Strike price in dollars
    expiration = Column(String(10), nullable=False)  # YYYY-MM-DD format
    dte_at_entry = Column(Integer, nullable=False)  # Days to expiration at entry
    premium_received = Column(Float, nullable=False)  # Premium in dollars
    contracts = Column(Integer, nullable=False, default=1)
    capital_required = Column(Float, nullable=False)  # Cash requirement in dollars
    delta_at_entry = Column(Float, nullable=False)  # Delta value (-1.0 to 0)
    realistic_yield_at_entry = Column(Float, nullable=False)  # Yield percentage
    entry_notes = Column(Text, nullable=True)
    entry_tech_score = Column(Integer, nullable=True)  # 0-100 tech score
    entry_pivot_daily = Column(Float, nullable=True)  # Daily pivot level
    entry_pivot_weekly = Column(Float, nullable=True)  # Weekly pivot level

    # Exit Information (nullable until trade is closed)
    exit_date = Column(DateTime, nullable=True)
    exit_type = Column(
        String(20),
        nullable=True,
        # Values: "expiration", "assignment", "bought_back", "manual_close"
    )
    close_price = Column(Float, nullable=True)  # Price when closed
    buy_back_price = Column(Float, nullable=True)  # Price paid to buy back
    exit_notes = Column(Text, nullable=True)

    # Performance Metrics
    realized_pnl = Column(Float, nullable=True)  # P&L in dollars
    roi_percent = Column(Float, nullable=True)  # ROI as decimal (0.05 = 5%)
    holding_days = Column(Integer, nullable=True)  # Days held
    annualized_roi = Column(Float, nullable=True)  # Annualized ROI
    status = Column(String(10), nullable=False, default="open")  # "open" or "closed"

    # Strategy Information (for multi-strategy support)
    strategy = Column(String(20), nullable=False, default="CSP", index=True)  # "CSP", "WHEEL", etc.
    strategy_metadata = Column(Text, nullable=True)  # JSON for strategy-specific data

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    flagged_for_review = Column(Boolean, nullable=False, default=False)

    # =========================================================================
    # Validation Methods (following data-quality-checker patterns)
    # =========================================================================

    @staticmethod
    def validate_symbol(symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Validate ticker symbol.

        Args:
            symbol: Ticker symbol (e.g., "AAPL")

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not symbol:
            return False, "Symbol is required"
        if not isinstance(symbol, str):
            return False, f"Symbol must be string, got {type(symbol).__name__}"

        symbol = symbol.upper().strip()
        if len(symbol) < 1 or len(symbol) > 5:
            return False, f"Symbol length must be 1-5 chars, got {len(symbol)}"
        if not symbol.isalpha():
            return False, f"Symbol must contain only letters, got '{symbol}'"

        return True, None

    @staticmethod
    def validate_price(price: float, field_name: str = "Price") -> Tuple[bool, Optional[str]]:
        """
        Validate a price field (strike, premium, etc).

        Args:
            price: Price value
            field_name: Name of field for error message

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            price_float = float(price)
        except (TypeError, ValueError):
            return False, f"{field_name} must be numeric, got {type(price).__name__}"

        if price_float <= 0:
            return False, f"{field_name} must be positive, got {price_float}"
        # Allow up to $1M for capital required (reasonable for options trading)
        if price_float > 1000000:
            return False, f"{field_name} exceeds reasonable limit: ${price_float}"

        return True, None

    @staticmethod
    def validate_dte(dte: int) -> Tuple[bool, Optional[str]]:
        """
        Validate Days To Expiration.

        Args:
            dte: DTE in days

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            dte_int = int(dte)
        except (TypeError, ValueError):
            return False, f"DTE must be integer, got {type(dte).__name__}"

        if dte_int < 1:
            return False, f"DTE must be at least 1 day, got {dte_int}"
        if dte_int > 730:
            return False, f"DTE must not exceed 730 days, got {dte_int}"

        return True, None

    @staticmethod
    def validate_delta(delta: float) -> Tuple[bool, Optional[str]]:
        """
        Validate delta value.

        Args:
            delta: Delta value (should be negative for puts)

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            delta_float = float(delta)
        except (TypeError, ValueError):
            return False, f"Delta must be numeric, got {type(delta).__name__}"

        # For puts, delta should be between -1 and 0
        if delta_float < -1.0 or delta_float > 0:
            return False, f"Delta out of range [-1, 0], got {delta_float}"

        return True, None

    @staticmethod
    def validate_date_string(date_str: str, field_name: str = "Date") -> Tuple[bool, Optional[str]]:
        """
        Validate date string in YYYY-MM-DD format.

        Args:
            date_str: Date string
            field_name: Name of field for error message

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(date_str, str):
            return False, f"{field_name} must be string, got {type(date_str).__name__}"

        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True, None
        except ValueError:
            return False, f"{field_name} must be YYYY-MM-DD format, got '{date_str}'"

    @staticmethod
    def validate_percentage(value: float, field_name: str = "Percentage") -> Tuple[bool, Optional[str]]:
        """
        Validate a percentage value.

        Args:
            value: Percentage value (e.g., 12.79 = 12.79%)
            field_name: Name of field for error message

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            value_float = float(value)
        except (TypeError, ValueError):
            return False, f"{field_name} must be numeric, got {type(value).__name__}"

        # Allow 0-100% range for realistic yield
        if value_float < 0 or value_float > 100:
            return False, f"{field_name} out of range [0, 100], got {value_float}"

        return True, None

    # =========================================================================
    # Factory Methods for Creation
    # =========================================================================

    @classmethod
    def create_from_dict(cls, data: Dict, session: Optional[Session] = None) -> 'Trade':
        """
        Create a new Trade from a dictionary, with full validation.

        Args:
            data: Dictionary of trade data
            session: Optional SQLAlchemy session for persistence

        Returns:
            Trade: Validated trade instance

        Raises:
            TradeValidationError: If validation fails
        """
        errors = []

        # Validate required fields
        required_fields = [
            'symbol', 'strike', 'expiration', 'dte_at_entry',
            'premium_received', 'contracts', 'capital_required',
            'delta_at_entry', 'realistic_yield_at_entry'
        ]
        for field in required_fields:
            if field not in data or data[field] is None:
                errors.append(f"Missing required field: {field}")

        if errors:
            raise TradeValidationError("; ".join(errors))

        # Validate individual fields
        valid, msg = cls.validate_symbol(data['symbol'])
        if not valid:
            errors.append(msg)

        valid, msg = cls.validate_price(data['strike'], 'Strike price')
        if not valid:
            errors.append(msg)

        valid, msg = cls.validate_date_string(data['expiration'], 'Expiration')
        if not valid:
            errors.append(msg)

        valid, msg = cls.validate_dte(data['dte_at_entry'])
        if not valid:
            errors.append(msg)

        valid, msg = cls.validate_price(data['premium_received'], 'Premium')
        if not valid:
            errors.append(msg)

        valid, msg = cls.validate_price(data['capital_required'], 'Capital required')
        if not valid:
            errors.append(msg)

        valid, msg = cls.validate_delta(data['delta_at_entry'])
        if not valid:
            errors.append(msg)

        valid, msg = cls.validate_percentage(data['realistic_yield_at_entry'], 'Realistic yield')
        if not valid:
            errors.append(msg)

        if errors:
            raise TradeValidationError("; ".join(errors))

        # Create trade instance
        trade = cls(
            symbol=data['symbol'].upper(),
            strike=float(data['strike']),
            expiration=data['expiration'],
            dte_at_entry=int(data['dte_at_entry']),
            premium_received=float(data['premium_received']),
            contracts=int(data.get('contracts', 1)),
            capital_required=float(data['capital_required']),
            delta_at_entry=float(data['delta_at_entry']),
            realistic_yield_at_entry=float(data['realistic_yield_at_entry']),
            entry_notes=data.get('entry_notes'),
            entry_tech_score=data.get('entry_tech_score'),
            entry_pivot_daily=data.get('entry_pivot_daily'),
            entry_pivot_weekly=data.get('entry_pivot_weekly'),
        )

        if session:
            session.add(trade)

        return trade

    def close_trade(self, exit_data: Dict) -> None:
        """
        Close a trade with exit information and calculate P&L.

        Args:
            exit_data: Dictionary with exit_type, buy_back_price, exit_notes, etc.

        Raises:
            TradeValidationError: If exit data is invalid
        """
        errors = []

        # Validate exit type
        valid_types = {'expiration', 'assignment', 'bought_back', 'manual_close'}
        if exit_data.get('exit_type') not in valid_types:
            errors.append(f"Invalid exit_type: must be one of {valid_types}")

        # Validate buy_back_price if trade was bought back
        if exit_data.get('exit_type') in {'assignment', 'bought_back'}:
            if 'buy_back_price' not in exit_data:
                errors.append("buy_back_price required for this exit type")
            else:
                valid, msg = self.validate_price(exit_data['buy_back_price'], 'Buy back price')
                if not valid:
                    errors.append(msg)

        if errors:
            raise TradeValidationError("; ".join(errors))

        # Set exit fields
        self.exit_date = datetime.utcnow()
        self.exit_type = exit_data['exit_type']
        self.buy_back_price = float(exit_data.get('buy_back_price', 0))
        self.close_price = float(exit_data.get('close_price', 0))
        self.exit_notes = exit_data.get('exit_notes')

        # Calculate P&L
        self.calculate_pnl()
        self.status = 'closed'

    def calculate_pnl(self) -> None:
        """
        Calculate P&L metrics for a closed trade.

        Protected against division by zero and NaN values.
        """
        if self.status != 'closed' or not self.exit_date:
            return

        try:
            # P&L in dollars: (premium received - buy_back_price) * 100 per contract
            buy_back = self.buy_back_price if self.buy_back_price else 0
            self.realized_pnl = (self.premium_received - buy_back) * 100 * self.contracts

            # ROI: P&L / capital required
            if self.capital_required > 0:
                self.roi_percent = self.realized_pnl / self.capital_required
            else:
                self.roi_percent = 0

            # Holding period
            if self.exit_date and self.entry_date:
                delta = self.exit_date - self.entry_date
                self.holding_days = delta.days

                # Annualized ROI
                if self.holding_days > 0:
                    self.annualized_roi = self.roi_percent * (365.0 / self.holding_days)
                else:
                    self.annualized_roi = self.roi_percent

        except (ZeroDivisionError, TypeError, AttributeError) as e:
            logger.error(f"Error calculating P&L for trade {self.id}: {str(e)}")
            # Leave metrics as None rather than storing invalid values

    def to_dict(self) -> Dict:
        """
        Convert trade to dictionary for JSON serialization.

        Returns:
            dict: Trade data as dictionary
        """
        return {
            'id': self.id,
            'entry_date': self.entry_date.isoformat() if self.entry_date else None,
            'symbol': self.symbol,
            'strike': self.strike,
            'expiration': self.expiration,
            'dte_at_entry': self.dte_at_entry,
            'premium_received': self.premium_received,
            'contracts': self.contracts,
            'capital_required': self.capital_required,
            'delta_at_entry': self.delta_at_entry,
            'realistic_yield_at_entry': self.realistic_yield_at_entry,
            'entry_notes': self.entry_notes,
            'entry_tech_score': self.entry_tech_score,
            'entry_pivot_daily': self.entry_pivot_daily,
            'entry_pivot_weekly': self.entry_pivot_weekly,
            'exit_date': self.exit_date.isoformat() if self.exit_date else None,
            'exit_type': self.exit_type,
            'close_price': self.close_price,
            'buy_back_price': self.buy_back_price,
            'exit_notes': self.exit_notes,
            'realized_pnl': self.realized_pnl,
            'roi_percent': self.roi_percent,
            'holding_days': self.holding_days,
            'annualized_roi': self.annualized_roi,
            'status': self.status,
            'strategy': self.strategy,
            'strategy_metadata': self.strategy_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<Trade {self.symbol} ${self.strike} "
            f"exp={self.expiration} status={self.status}>"
        )
