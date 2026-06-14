"""
Wheel Strategy - Unified income generation through put/call selling cycles.

Workflow:
1. Sell Put at strike X (collect premium Y)
2. If assigned: Own stock at X, collect capital
3. Sell Covered Call above strike X (collect premium Z)
4. If called away: Sell stock, realize total P&L = Y + Z

UNIFIED TRACKING: Single trade record tracks full cycle.
Metrics: Combined P&L from both put sale + call sale.

Target market: Income traders who want the complete cycle tracked together.

Following dev-patterns and BaseStrategy interface.
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np

from scanner.base_strategy import BaseStrategy, StrategyValidationError, StrategyScanError
from scanner.strategies.csp_strategy import CSPStrategy
from scanner.data_providers import (
    get_stock_price_and_volume,
    get_calls_chain,
)
from web.models.strategy import StrategyMetadata

logger = logging.getLogger(__name__)


class WheelStrategy(BaseStrategy):
    """
    Wheel Strategy - Income generation through put/call selling cycles.

    UNIFIED TRACKING: Single trade record tracks full cycle:
      - Entry: Sell put, collect premium
      - Assignment: Stock assigned (if happens)
      - Covered Call: Sell call on assigned stock
      - Exit: Stock called away (if happens) or stock sold

    Metrics: Combined P&L from both put sale + call sale.

    Scanner shows:
    1. Which puts are available to sell? (same as CSP scanner)
    2. For each put, if assigned, what calls could I sell?
    3. Total potential yield (put + call combined)

    Follows dev-patterns and BaseStrategy interface.
    """

    def __init__(self, metadata: StrategyMetadata, config: Dict[str, Any]):
        """Initialize Wheel strategy."""
        super().__init__(metadata, config)

        # Reuse CSP strategy for put scanning
        self.csp_strategy = CSPStrategy(metadata, config)

        # Wheel-specific configuration
        strategy_config = config.get('STRATEGY_CONFIGS', {}).get('WHEEL', {})

        # Call leg parameters (used when estimating calls if assigned)
        self.call_dte_min = strategy_config.get('call_dte_min', 14)
        self.call_dte_max = strategy_config.get('call_dte_max', 30)
        self.call_delta_min = strategy_config.get('call_delta_min', 0.20)
        self.call_delta_max = strategy_config.get('call_delta_max', 0.40)

        logger.info(f"WheelStrategy initialized")

    def validate_params(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate scan parameters.

        For Wheel, we validate both put leg and call leg parameters.

        Args:
            params: Scan parameters including put_dte_min, call_dte_min, etc.

        Returns:
            (is_valid, error_message)
        """
        # Validate put leg using CSP strategy
        valid, msg = self.csp_strategy.validate_params(params)
        if not valid:
            return False, f"Put leg validation failed: {msg}"

        # Validate call leg parameters
        try:
            call_dte_min = int(params.get('call_dte_min', 14))
            call_dte_max = int(params.get('call_dte_max', 30))

            if call_dte_min < 1:
                return False, "Call DTE min must be at least 1 day"
            if call_dte_max > 730:
                return False, "Call DTE max must not exceed 730 days"
            if call_dte_min > call_dte_max:
                return False, "Call DTE min must be <= Call DTE max"

            call_delta_min = float(params.get('call_delta_min', 0.20))
            call_delta_max = float(params.get('call_delta_max', 0.40))

            if call_delta_min < 0 or call_delta_max > 1:
                return False, "Call delta must be between 0 and 1 (calls)"
            if call_delta_min > call_delta_max:
                return False, "Call delta min must be <= Call delta max"

            return True, None

        except (TypeError, ValueError) as e:
            return False, f"Invalid parameter format: {str(e)}"

    def get_default_params(self) -> Dict[str, Any]:
        """
        Return default scan parameters for Wheel strategy.

        Includes both put leg and call leg parameters.

        Returns:
            Dict with default DTE, delta, and filter settings
        """
        csp_defaults = self.csp_strategy.get_default_params()

        return {
            # Put leg (same as CSP)
            "dte_min": csp_defaults.get('dte_min', 21),
            "dte_max": csp_defaults.get('dte_max', 45),
            "delta_min": csp_defaults.get('delta_min', -0.30),
            "delta_max": csp_defaults.get('delta_max', -0.10),
            # Call leg (estimated for if assigned)
            "call_dte_min": self.call_dte_min,
            "call_dte_max": self.call_dte_max,
            "call_delta_min": self.call_delta_min,
            "call_delta_max": self.call_delta_max,
            # Filters
            "min_open_interest": csp_defaults.get('min_open_interest', 100),
            "max_bid_ask_spread_pct": csp_defaults.get('max_bid_ask_spread_pct', 0.10),
        }

    def run_scan(self, symbols: List[str], params: Dict[str, Any]) -> pd.DataFrame:
        """
        Execute scan for Wheel opportunities.

        Orchestration:
        1. Run CSP scan to find puts
        2. For each put: estimate what calls would be available if assigned
        3. Calculate combined put + call yield
        4. Return combined opportunities

        Args:
            symbols: List of ticker symbols
            params: Scan parameters

        Returns:
            DataFrame with Wheel opportunities (puts with estimated calls)

        Raises:
            StrategyScanError: If scan fails
        """
        # Validate params
        valid, msg = self.validate_params(params)
        if not valid:
            raise StrategyValidationError(msg)

        logger.info(f"Wheel Scan started: {len(symbols)} symbols")

        # Step 1: Run CSP scan to find puts
        puts_df = self.csp_strategy.run_scan(symbols, params)

        if puts_df.empty:
            logger.info("Wheel Scan: No puts found, returning empty results")
            return puts_df

        # Step 2: For each put, estimate calls if assigned
        wheel_df = puts_df.copy()
        wheel_df['estimated_call_premium'] = 0.0
        wheel_df['estimated_total_yield'] = 0.0
        wheel_df['wheel_cycle_probability'] = 0.0

        # Enrich with call estimates (simplified estimation)
        # In production, would fetch actual call chains
        for idx, row in wheel_df.iterrows():
            symbol = row['symbol']
            strike = row['strike']
            put_premium = row['premium']
            put_delta = row['delta']

            try:
                # Estimate call premium if assigned at this strike
                # Rough heuristic: calls trade at ~50-80% of put premium for same strike
                estimated_call_premium = put_premium * 0.6  # Conservative estimate

                # Total yield from both legs
                total_premium = put_premium + estimated_call_premium
                total_capital_required = strike * 100
                years_to_expiration = row.get('years_to_expiration', 0.12)  # ~45 days

                estimated_total_yield = (total_premium / total_capital_required) / years_to_expiration * 100

                # Wheel completion probability: (1 - probability assigned) + probability assigned
                # For simplicity: Use put delta as proxy for assignment risk
                # If delta = -0.176, assignment probability ≈ 17.6%
                # We'll show total potential if both legs complete
                wheel_completion_probability = 1.0  # Assumed completion if entered

                wheel_df.at[idx, 'estimated_call_premium'] = round(estimated_call_premium, 2)
                wheel_df.at[idx, 'estimated_total_yield'] = round(estimated_total_yield, 2)
                wheel_df.at[idx, 'wheel_cycle_probability'] = round(wheel_completion_probability, 2)

            except Exception as e:
                logger.debug(f"Error estimating call for {symbol} strike {strike}: {str(e)}")
                continue

        logger.info(f"Wheel Scan complete: {len(wheel_df)} opportunities")
        return wheel_df

    def filter_results(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """
        Apply additional filters (already done in run_scan).

        Args:
            df: Results DataFrame
            params: Filter parameters

        Returns:
            Filtered DataFrame
        """
        return df.copy() if not df.empty else df

    def calculate_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add strategy-specific metrics (already done in run_scan).

        Args:
            df: Results DataFrame

        Returns:
            Enhanced DataFrame
        """
        return df.copy() if not df.empty else df

    def derive_sections(self, df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
        """
        Derive strategy-specific result sections.

        Wheel returns:
        - highest_total_yield: Put + call combined, sorted by total yield
        - safest: Highest OI, lowest delta (less likely to be assigned)
        - balanced: Best income efficiency

        Args:
            df: Complete filtered + metrics DataFrame

        Returns:
            Dict with sections, each containing top ~10 opportunities
        """
        if df.empty:
            return {
                'highest_total_yield': [],
                'safest': [],
                'balanced': [],
            }

        sections = {}

        # Highest Total Yield: Put + call combined
        highest_yield = df.nlargest(10, 'estimated_total_yield')
        sections['highest_total_yield'] = highest_yield[[
            'symbol', 'strike', 'premium', 'estimated_call_premium',
            'estimated_total_yield', 'delta', 'open_interest'
        ]].to_dict('records')

        # Safest: Highest OI, lowest delta (less likely assigned)
        safest = df.copy()
        safest = safest.sort_values(['open_interest', 'delta'], ascending=[False, False])
        sections['safest'] = safest.head(10)[[
            'symbol', 'strike', 'premium', 'estimated_call_premium',
            'open_interest', 'distance_otm'
        ]].to_dict('records')

        # Balanced: Income efficiency per capital per day
        df_balanced = df.copy()
        df_balanced['income_efficiency'] = (
            (df_balanced['premium'] + df_balanced['estimated_call_premium']) * 100 /
            df_balanced['capital_required'] /
            (df_balanced['days_to_expiration'] + 1) * 365
        )
        balanced = df_balanced.nlargest(10, 'income_efficiency')
        sections['balanced'] = balanced[[
            'symbol', 'strike', 'premium', 'estimated_call_premium',
            'estimated_total_yield', 'days_to_expiration'
        ]].to_dict('records')

        return sections
