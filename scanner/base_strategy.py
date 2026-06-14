"""
Abstract base class for all trading strategies.

All strategies must implement this interface.
This enables scanner orchestration to work with any strategy via polymorphism.

Design Pattern: Strategy Pattern (Gang of Four)
Reference: .claude/referenced-skills/dev-patterns/
"""

from abc import ABC, abstractmethod
from pandas import DataFrame
from typing import Tuple, Dict, Any, List, Optional
from web.models.strategy import StrategyMetadata


class BaseStrategy(ABC):
    """
    Abstract strategy interface.

    All concrete strategies (CSP, Wheel, Call Spread, etc.) inherit from this
    and implement the abstract methods. Scanner code doesn't need to know about
    individual strategy implementations - it just calls these methods.

    This ensures:
    - New strategies can be added without changing scanner code
    - Each strategy is isolated and testable
    - UI can adapt based on strategy metadata
    """

    def __init__(self, metadata: StrategyMetadata, config: Dict[str, Any]):
        """
        Initialize strategy with metadata and configuration.

        Args:
            metadata: StrategyMetadata instance (name, description, etc.)
            config: Configuration dict from web/config.py
        """
        self.metadata = metadata
        self.config = config

    @abstractmethod
    def validate_params(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate scan parameters for this strategy.

        Args:
            params: User-supplied scan parameters
                Example: {"dte_min": 21, "dte_max": 45, "delta_min": -0.20}

        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if params are valid
            - error_message: User-friendly error if invalid, None if valid
        """
        pass

    @abstractmethod
    def get_default_params(self) -> Dict[str, Any]:
        """
        Return default scan parameters for this strategy.

        Called when user hasn't specified params, providing sensible defaults
        based on strategy type.

        Returns:
            Dict with keys like:
            - dte_min, dte_max: Days to expiration window
            - delta_min, delta_max: Delta range for filtering
            - min_open_interest: Minimum open interest
            - max_bid_ask_spread_pct: Maximum spread tolerance
            - (plus strategy-specific params)
        """
        pass

    @abstractmethod
    def run_scan(self, symbols: List[str], params: Dict[str, Any]) -> DataFrame:
        """
        Execute scan for given symbols and parameters.

        Orchestration:
        1. Validate params (should already be done, but double-check)
        2. For each symbol:
           - Get stock data (current price, volume)
           - Get options chains (puts, calls, expirations)
           - Calculate Greeks and metrics
           - Apply filters
        3. Return DataFrame with all opportunities

        Args:
            symbols: List of ticker symbols to scan
            params: Validated scan parameters

        Returns:
            DataFrame with columns (strategy-specific, but includes):
            - symbol, strike, expiry_date, dte, premium, delta
            - bid, ask, open_interest
            - (strategy-specific: realistic_yield, risk_adjusted_yield, etc.)

        Raises:
            ValueError: If scan fails (bad data, API error, etc.)
        """
        pass

    @abstractmethod
    def filter_results(self, df: DataFrame, params: Dict[str, Any]) -> DataFrame:
        """
        Apply strategy-specific filters to results.

        Removes opportunities that don't meet criteria:
        - DTE in valid window
        - Delta in target range
        - Open interest above threshold
        - Bid-ask spread below tolerance
        - (strategy-specific filters)

        Args:
            df: DataFrame from run_scan()
            params: Scan parameters (contains filter thresholds)

        Returns:
            Filtered DataFrame (subset of input)
        """
        pass

    @abstractmethod
    def calculate_metrics(self, df: DataFrame) -> DataFrame:
        """
        Add strategy-specific metrics to results.

        Enriches DataFrame with calculated columns:

        CSP:
        - realistic_yield: (Premium / Capital) adjusted by delta
        - risk_adjusted_yield: (Premium / Risk) * years
        - capital_required: Strike * 100

        Wheel:
        - Same as CSP, plus:
        - estimated_call_premium: If assigned, what calls available?
        - total_potential_yield: Put + call premiums combined

        Call Spread:
        - max_profit: Width * 100
        - max_loss: Credit - Max Profit
        - profit_probability: Delta-based estimate

        Args:
            df: DataFrame (already filtered)

        Returns:
            Enriched DataFrame with additional metric columns
        """
        pass

    @abstractmethod
    def derive_sections(self, df: DataFrame) -> Dict[str, List[Dict[str, Any]]]:
        """
        Derive strategy-specific result sections.

        Splits results into sorted groups for UI display.
        Each section shows top N opportunities sorted by different criteria.

        CSP returns:
        {
            'flagged': [...],           # Realistic yield >= 10%
            'safest': [...],            # Highest OI, lowest delta
            'balanced': [...],          # Best income efficiency
            'highest_yield': [...]      # Sorted by risk_adjusted_yield
        }

        Wheel returns:
        {
            'highest_total_yield': [...],  # Put + call combined
            'safest': [...],
            'balanced': [...]
        }

        Args:
            df: Complete filtered + metrics DataFrame

        Returns:
            Dict where each value is a list of dicts (top ~10 per section)
            Each dict is a row from the DataFrame converted to JSON-serializable format
        """
        pass


class StrategyValidationError(ValueError):
    """Raised when strategy validation fails."""
    pass


class StrategyScanError(RuntimeError):
    """Raised when strategy scan fails."""
    pass
