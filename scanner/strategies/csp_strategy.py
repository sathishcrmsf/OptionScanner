"""
CSP (Cash-Secured Put) selling strategy implementation.

Scan for puts to sell for income generation.
Filters by: DTE, delta, open interest, bid-ask spread.
Metrics: premium, realistic yield, risk-adjusted yield.

Refactored from original options_scanner.py to fit BaseStrategy interface.

Following dev-patterns error handling and validation.
Reference: options_scanner.py (original CSP implementation)
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from scanner.base_strategy import BaseStrategy, StrategyValidationError, StrategyScanError
from scanner.data_providers import (
    get_stock_price_and_volume,
    get_puts_chain,
)
from scanner.indicators import calculate_greeks
from web.models.strategy import StrategyMetadata

logger = logging.getLogger(__name__)


class CSPStrategy(BaseStrategy):
    """
    Cash-Secured Put selling strategy.

    Scan for puts to sell for income generation.
    Filters by: DTE, delta, open interest, bid-ask spread.
    Metrics: premium, realistic yield, risk-adjusted yield.
    Sections: flagged (high yield), safest, balanced, highest_yield.

    Follows dev-patterns error handling and validation.
    Used as Phase 1 of the Wheel strategy (also standalone).
    """

    def __init__(self, metadata: StrategyMetadata, config: Dict[str, Any]):
        """Initialize CSP strategy."""
        super().__init__(metadata, config)

        # Configuration thresholds (from web/config.py)
        strategy_config = config.get('STRATEGY_CONFIGS', {}).get('CSP', {})

        self.min_open_interest = strategy_config.get('min_open_interest', 100)
        self.min_avg_volume = strategy_config.get('min_avg_volume', 1_000_000)
        self.max_bid_ask_spread_pct = strategy_config.get('max_bid_ask_spread_pct', 0.10)
        self.flag_min_yield = strategy_config.get('flag_min_yield', 10.0)

        logger.info(f"CSPStrategy initialized with config: {strategy_config}")

    def validate_params(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate scan parameters.

        Args:
            params: User-supplied scan parameters

        Returns:
            (is_valid, error_message)
        """
        try:
            # Validate DTE range
            dte_min = int(params.get('dte_min', 21))
            dte_max = int(params.get('dte_max', 45))

            if dte_min < 1:
                return False, "DTE min must be at least 1 day"
            if dte_max > 730:
                return False, "DTE max must not exceed 730 days"
            if dte_min > dte_max:
                return False, "DTE min must be <= DTE max"

            # Validate delta range
            delta_min = float(params.get('delta_min', -0.30))
            delta_max = float(params.get('delta_max', -0.10))

            if delta_min < -1.0 or delta_max > 0:
                return False, "Delta must be between -1.0 and 0 (puts)"
            if delta_min > delta_max:
                return False, "Delta min must be <= Delta max"

            # Validate account size if provided
            account_size = params.get('account_size')
            if account_size is not None:
                account_size = float(account_size)
                if account_size < 5000:
                    return False, "Account size must be at least $5,000"

            return True, None

        except (TypeError, ValueError) as e:
            return False, f"Invalid parameter format: {str(e)}"

    def get_default_params(self) -> Dict[str, Any]:
        """
        Return default scan parameters for CSP strategy.

        Returns:
            Dict with default DTE, delta, and filter settings
        """
        return {
            "dte_min": 21,
            "dte_max": 45,
            "delta_min": -0.30,
            "delta_max": -0.10,
            "min_open_interest": self.min_open_interest,
            "max_bid_ask_spread_pct": self.max_bid_ask_spread_pct,
        }

    def run_scan(self, symbols: List[str], params: Dict[str, Any]) -> pd.DataFrame:
        """
        Execute scan for CSP opportunities.

        Orchestration:
        1. Validate parameters
        2. For each symbol:
           - Get stock data (price, volume)
           - Get puts chains
           - Calculate metrics
           - Apply filters
        3. Return combined DataFrame

        Args:
            symbols: List of ticker symbols
            params: Scan parameters

        Returns:
            DataFrame with all qualifying puts

        Raises:
            StrategyScanError: If scan fails
        """
        # Validate params
        valid, msg = self.validate_params(params)
        if not valid:
            raise StrategyValidationError(msg)

        dte_min = int(params.get('dte_min', 21))
        dte_max = int(params.get('dte_max', 45))
        delta_min = float(params.get('delta_min', -0.30))
        delta_max = float(params.get('delta_max', -0.10))

        logger.info(f"CSP Scan started: {len(symbols)} symbols, DTE {dte_min}-{dte_max}, Delta {delta_min}-{delta_max}")

        all_opportunities = []

        for symbol in symbols:
            try:
                # Get stock data
                stock_data = get_stock_price_and_volume(symbol)
                if not stock_data:
                    logger.warning(f"Could not get stock data for {symbol}")
                    continue

                # Filter by average volume
                if stock_data['average_volume'] < self.min_avg_volume:
                    logger.debug(f"Skipping {symbol}: volume {stock_data['average_volume']} < {self.min_avg_volume}")
                    continue

                # Get puts chains
                puts_df = get_puts_chain(symbol)
                if puts_df is None or puts_df.empty:
                    logger.debug(f"No puts chain for {symbol}")
                    continue

                # Calculate metrics and filter
                opportunities = self._filter_and_calculate(
                    symbol,
                    puts_df,
                    stock_data,
                    dte_min,
                    dte_max,
                    delta_min,
                    delta_max,
                )

                all_opportunities.extend(opportunities)
                logger.info(f"Found {len(opportunities)} qualifying puts for {symbol}")

            except Exception as e:
                logger.warning(f"Error scanning {symbol}: {str(e)}")
                continue

        logger.info(f"CSP Scan complete: {len(all_opportunities)} total opportunities")

        # Convert to DataFrame
        if not all_opportunities:
            return pd.DataFrame()

        return pd.DataFrame(all_opportunities)

    def _filter_and_calculate(
        self,
        symbol: str,
        puts_df: pd.DataFrame,
        stock_data: Dict[str, Any],
        dte_min: int,
        dte_max: int,
        delta_min: float,
        delta_max: float,
    ) -> List[Dict[str, Any]]:
        """
        Filter puts and calculate metrics.

        Args:
            symbol: Stock symbol
            puts_df: DataFrame from get_puts_chain
            stock_data: Dict with current_price, average_volume
            dte_min, dte_max: DTE window
            delta_min, delta_max: Delta range

        Returns:
            List of dicts (each is a qualifying put)
        """
        opportunities = []
        stock_price = stock_data['current_price']

        # Enrich with Greeks if missing
        puts_df = self._enrich_with_greeks(puts_df, stock_price)

        for _, row in puts_df.iterrows():
            try:
                metrics = self._calculate_metrics(row, stock_price)
                if not metrics:
                    continue

                dte = metrics['days_to_expiration']

                # Apply filters in order
                if not (dte_min <= dte <= dte_max):
                    continue
                if metrics['strike'] >= stock_price:
                    continue
                if not (delta_min <= metrics['delta'] <= delta_max):
                    continue
                if metrics['open_interest'] < self.min_open_interest:
                    continue
                if metrics['bid_ask_spread_pct'] >= self.max_bid_ask_spread_pct:
                    continue

                # All filters passed
                opportunity = {
                    'symbol': symbol,
                    'current_price': stock_price,
                    **metrics,
                }

                opportunities.append(opportunity)

            except Exception as e:
                logger.debug(f"Error processing put for {symbol}: {str(e)}")
                continue

        return opportunities

    def _enrich_with_greeks(self, puts_df: pd.DataFrame, stock_price: float) -> pd.DataFrame:
        """
        Compute Greeks if missing from data source.

        Args:
            puts_df: DataFrame from data provider
            stock_price: Current stock price (for Greeks calculation)

        Returns:
            DataFrame with delta, theta, etc.
        """
        df = puts_df.copy()

        # Normalize column names
        if 'impliedVolatility' in df.columns and 'implied_volatility' not in df.columns:
            df['implied_volatility'] = df['impliedVolatility']
        if 'openInterest' in df.columns and 'open_interest' not in df.columns:
            df['open_interest'] = df['openInterest']

        # Calculate Greeks if missing
        if 'delta' not in df.columns or df['delta'].isna().any():
            df['option_type'] = 'put'
            df['expiration'] = pd.to_datetime(df['expiration'])
            df = calculate_greeks(df, underlying_price=stock_price)

        return df

    def _calculate_metrics(self, row: pd.Series, stock_price: float) -> Optional[Dict[str, Any]]:
        """
        Calculate all required metrics for a put contract.

        Args:
            row: Single row from puts DataFrame
            stock_price: Current stock price

        Returns:
            Dict with metrics, or None if calculation fails
        """
        try:
            strike = float(row['strike'])
            bid = float(row['bid'])
            ask = float(row['ask'])
            premium = (bid + ask) / 2  # Midpoint
            delta = float(row.get('delta', np.nan))
            theta_raw = float(row.get('theta', 0.0))
            iv = float(row.get('implied_volatility', 0.0))
            open_interest = int(row.get('open_interest', 0))
            expiration_str = str(row['expiration'])[:10]

            # Validate required fields
            if pd.isna(delta) or pd.isna(expiration_str):
                return None

            # Calculate days to expiration
            expiration_date = datetime.strptime(expiration_str, '%Y-%m-%d')
            days_to_expiration = (expiration_date - datetime.utcnow()).days
            years_to_expiration = max(days_to_expiration / 365.0, 0.001)

            # Calculate yields
            annualized_yield = (premium / strike) / years_to_expiration * 100 if strike > 0 else 0
            risk_adjusted_yield = (premium / (strike - premium)) / years_to_expiration * 100 if strike > premium else 0
            realistic_yield = risk_adjusted_yield * (1 + delta)

            # Distance OTM
            distance_otm = ((stock_price - strike) / stock_price) * 100 if stock_price > 0 else 0

            # Bid-ask spread
            bid_ask_spread = ask - bid
            bid_ask_spread_pct = bid_ask_spread / premium if premium > 0 else float('inf')

            # Capital required
            capital_required = strike * 100

            # Theta per contract
            theta_per_contract = theta_raw * 100

            return {
                'strike': strike,
                'premium': premium,
                'bid': bid,
                'ask': ask,
                'delta': delta,
                'theta_per_contract': round(theta_per_contract, 2),
                'implied_volatility': round(iv * 100, 2),
                'open_interest': open_interest,
                'expiration': expiration_str,
                'days_to_expiration': days_to_expiration,
                'years_to_expiration': years_to_expiration,
                'annualized_yield': round(annualized_yield, 2),
                'risk_adjusted_yield': round(risk_adjusted_yield, 2),
                'realistic_yield': round(realistic_yield, 2),
                'distance_otm': round(distance_otm, 2),
                'bid_ask_spread': round(bid_ask_spread, 4),
                'bid_ask_spread_pct': round(bid_ask_spread_pct, 4),
                'capital_required': capital_required,
            }

        except (TypeError, ValueError, KeyError) as e:
            logger.debug(f"Error calculating metrics: {str(e)}")
            return None

    def filter_results(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """
        Apply additional filters to results (already done in run_scan).

        Args:
            df: Results DataFrame
            params: Filter parameters

        Returns:
            Filtered DataFrame
        """
        # All filtering done in run_scan, this is a pass-through
        return df.copy() if not df.empty else df

    def calculate_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add strategy-specific metrics (already done in run_scan).

        Args:
            df: Results DataFrame

        Returns:
            Enhanced DataFrame
        """
        # All metrics already calculated in run_scan, this is a pass-through
        return df.copy() if not df.empty else df

    def derive_sections(self, df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
        """
        Derive strategy-specific result sections.

        CSP returns:
        - flagged: Realistic yield >= 10%
        - safest: Highest OI, lowest delta
        - balanced: Best income efficiency
        - highest_yield: Sorted by risk_adjusted_yield

        Args:
            df: Complete filtered + metrics DataFrame

        Returns:
            Dict with sections, each containing top ~10 opportunities
        """
        if df.empty:
            return {
                'flagged': [],
                'safest': [],
                'balanced': [],
                'highest_yield': [],
            }

        sections = {}

        # Flagged: High yield opportunities
        flagged = df[df['realistic_yield'] >= self.flag_min_yield].copy()
        sections['flagged'] = flagged.nlargest(10, 'realistic_yield')[['symbol', 'strike', 'premium', 'delta', 'realistic_yield', 'open_interest', 'days_to_expiration']].to_dict('records')

        # Safest: Highest OI, lowest delta (more conservative)
        safest = df.copy()
        safest = safest.sort_values(['open_interest', 'delta'], ascending=[False, False])
        sections['safest'] = safest.head(10)[['symbol', 'strike', 'premium', 'delta', 'open_interest', 'distance_otm']].to_dict('records')

        # Balanced: Income efficiency (premium per day per capital)
        df_balanced = df.copy()
        df_balanced['income_efficiency'] = (df_balanced['premium'] * 100) / df_balanced['capital_required'] / (df_balanced['days_to_expiration'] + 1) * 365
        balanced = df_balanced.nlargest(10, 'income_efficiency')
        sections['balanced'] = balanced[['symbol', 'strike', 'premium', 'delta', 'realistic_yield', 'days_to_expiration']].to_dict('records')

        # Highest Yield: Sorted by risk-adjusted yield
        highest_yield = df.nlargest(10, 'risk_adjusted_yield')
        sections['highest_yield'] = highest_yield[['symbol', 'strike', 'premium', 'delta', 'risk_adjusted_yield', 'open_interest']].to_dict('records')

        return sections
