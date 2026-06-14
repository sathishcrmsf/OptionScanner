"""
Performance analytics service for CSP trade analysis.

Calculates professional trader metrics: win rate, ROI, Sharpe ratio, etc.
All calculations protected against division by zero and NaN values.

Reference: .claude/referenced-skills/portfolio-manager/scripts/portfolio_analyzer.py
Advisory mode only - generates analysis, no automatic order placement.
"""

import logging
import math
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from statistics import mean, stdev

logger = logging.getLogger(__name__)

# Risk-free rate for Sharpe calculation (annual, as decimal)
RISK_FREE_RATE = 0.02  # 2% annual


class PerformanceCalculationError(ValueError):
    """Raised when performance calculation fails."""
    pass


class PerformanceService:
    """Calculate performance metrics for CSP trades."""

    @staticmethod
    def calculate_win_rate(trades: List[Dict]) -> Tuple[float, int, int]:
        """
        Calculate win rate from closed trades.

        A winning trade has realized_pnl > 0.

        Args:
            trades: List of trade dictionaries (closed trades)

        Returns:
            Tuple of (win_rate_pct, wins, total_closed)
                - win_rate_pct: Percentage 0-100
                - wins: Number of winning trades
                - total_closed: Total closed trades
        """
        if not trades:
            return 0.0, 0, 0

        closed_trades = [t for t in trades if t.get('status') == 'closed']
        if not closed_trades:
            return 0.0, 0, 0

        wins = sum(1 for t in closed_trades if (t.get('realized_pnl') or 0) > 0)
        total = len(closed_trades)

        if total == 0:
            return 0.0, 0, 0

        win_rate = (wins / total) * 100.0
        return win_rate, wins, total

    @staticmethod
    def calculate_average_roi(trades: List[Dict]) -> Tuple[float, int]:
        """
        Calculate average ROI from closed trades.

        Args:
            trades: List of trade dictionaries (closed trades)

        Returns:
            Tuple of (avg_roi_pct, trade_count)
                - avg_roi_pct: Average ROI as percentage
                - trade_count: Number of trades included
        """
        closed_trades = [
            t for t in trades
            if t.get('status') == 'closed' and t.get('roi_percent') is not None
        ]

        if not closed_trades:
            return 0.0, 0

        roi_values = [t['roi_percent'] for t in closed_trades]
        avg_roi = mean(roi_values) if roi_values else 0.0

        return avg_roi * 100.0, len(closed_trades)

    @staticmethod
    def calculate_total_pnl(trades: List[Dict]) -> float:
        """
        Calculate total realized P&L from all closed trades.

        Args:
            trades: List of trade dictionaries

        Returns:
            float: Total P&L in dollars
        """
        closed_trades = [
            t for t in trades
            if t.get('status') == 'closed' and t.get('realized_pnl') is not None
        ]

        if not closed_trades:
            return 0.0

        try:
            total = sum(float(t['realized_pnl']) for t in closed_trades)
            return round(total, 2)
        except (TypeError, ValueError) as e:
            logger.error(f"Error calculating total P&L: {str(e)}")
            return 0.0

    @staticmethod
    def calculate_sharpe_ratio(
        trades: List[Dict],
        risk_free_rate: float = RISK_FREE_RATE
    ) -> Tuple[float, int]:
        """
        Calculate Sharpe ratio from trade returns.

        Sharpe = (Avg Return - Risk-Free Rate) / Std Dev of Returns

        Args:
            trades: List of trade dictionaries
            risk_free_rate: Annual risk-free rate (as decimal, e.g., 0.02 = 2%)

        Returns:
            Tuple of (sharpe_ratio, trade_count)
                - sharpe_ratio: Sharpe ratio value
                - trade_count: Number of trades used
        """
        closed_trades = [
            t for t in trades
            if t.get('status') == 'closed'
            and t.get('realized_pnl') is not None
            and t.get('capital_required', 0) > 0
        ]

        if len(closed_trades) < 2:
            return 0.0, len(closed_trades)

        try:
            # Calculate daily returns
            returns = []
            for trade in closed_trades:
                roi = trade.get('roi_percent', 0)
                holding_days = trade.get('holding_days', 1)

                if holding_days > 0:
                    daily_return = roi / holding_days
                    returns.append(daily_return)

            if len(returns) < 2:
                return 0.0, len(closed_trades)

            avg_return = mean(returns)
            std_dev = stdev(returns)

            # Protect against division by zero
            if std_dev == 0:
                return 0.0, len(closed_trades)

            # Annual Sharpe ratio
            daily_rf = risk_free_rate / 365.0
            sharpe = (avg_return - daily_rf) / std_dev * math.sqrt(252)  # 252 trading days

            return round(sharpe, 4), len(closed_trades)

        except (ZeroDivisionError, ValueError, TypeError) as e:
            logger.error(f"Error calculating Sharpe ratio: {str(e)}")
            return 0.0, len(closed_trades)

    @staticmethod
    def calculate_max_drawdown(trades: List[Dict]) -> Tuple[float, int]:
        """
        Calculate maximum drawdown from cumulative P&L.

        Args:
            trades: List of trade dictionaries (should be sorted by entry date)

        Returns:
            Tuple of (max_drawdown_pct, trade_count)
                - max_drawdown_pct: Maximum drawdown as percentage
                - trade_count: Number of trades used
        """
        closed_trades = [
            t for t in trades
            if t.get('status') == 'closed'
            and t.get('realized_pnl') is not None
        ]

        if not closed_trades:
            return 0.0, 0

        try:
            # Calculate cumulative P&L
            cumulative = 0.0
            peak = 0.0
            max_dd = 0.0

            for trade in closed_trades:
                pnl = float(trade['realized_pnl'])
                cumulative += pnl

                if cumulative > peak:
                    peak = cumulative

                if peak > 0:
                    drawdown = (peak - cumulative) / peak
                    if drawdown > max_dd:
                        max_dd = drawdown

            return round(max_dd * 100.0, 2), len(closed_trades)

        except (TypeError, ValueError, ZeroDivisionError) as e:
            logger.error(f"Error calculating max drawdown: {str(e)}")
            return 0.0, len(closed_trades)

    @staticmethod
    def analyze_by_delta_band(trades: List[Dict]) -> Dict[str, Dict]:
        """
        Analyze performance by delta band (risk category).

        Delta bands:
        - Conservative: |Δ| ≤ 0.15 (safer, lower premium)
        - Standard: |Δ| 0.15-0.22 (balanced)
        - Aggressive: |Δ| > 0.22 (riskier, higher premium)

        Args:
            trades: List of trade dictionaries

        Returns:
            Dict with analysis by band
        """
        bands = {
            'conservative': {'min': 0, 'max': 0.15, 'trades': []},
            'standard': {'min': 0.15, 'max': 0.22, 'trades': []},
            'aggressive': {'min': 0.22, 'max': 1.0, 'trades': []},
        }

        # Categorize trades
        for trade in trades:
            delta = abs(trade.get('delta_at_entry', 0))
            if delta <= 0.15:
                bands['conservative']['trades'].append(trade)
            elif delta <= 0.22:
                bands['standard']['trades'].append(trade)
            else:
                bands['aggressive']['trades'].append(trade)

        # Calculate metrics for each band
        result = {}
        for band_name, band_data in bands.items():
            band_trades = band_data['trades']
            if not band_trades:
                result[band_name] = {
                    'total_trades': 0,
                    'closed_trades': 0,
                    'win_rate': 0.0,
                    'avg_roi': 0.0,
                    'total_pnl': 0.0,
                }
            else:
                win_rate, wins, closed = PerformanceService.calculate_win_rate(band_trades)
                avg_roi, _ = PerformanceService.calculate_average_roi(band_trades)
                total_pnl = PerformanceService.calculate_total_pnl(band_trades)

                result[band_name] = {
                    'total_trades': len(band_trades),
                    'closed_trades': closed,
                    'win_rate': round(win_rate, 2),
                    'avg_roi': round(avg_roi, 2),
                    'total_pnl': round(total_pnl, 2),
                }

        return result

    @staticmethod
    def analyze_by_dte_window(trades: List[Dict]) -> Dict[str, Dict]:
        """
        Analyze performance by DTE (Days to Expiration) window.

        Windows:
        - Weekly: 1-7 days
        - Short-term: 8-21 days
        - Medium-term: 22-45 days
        - Long-term: 46+ days

        Args:
            trades: List of trade dictionaries

        Returns:
            Dict with analysis by DTE window
        """
        windows = {
            'weekly': {'min': 1, 'max': 7, 'trades': []},
            'short_term': {'min': 8, 'max': 21, 'trades': []},
            'medium_term': {'min': 22, 'max': 45, 'trades': []},
            'long_term': {'min': 46, 'max': 730, 'trades': []},
        }

        # Categorize trades
        for trade in trades:
            dte = trade.get('dte_at_entry', 0)
            if dte <= 7:
                windows['weekly']['trades'].append(trade)
            elif dte <= 21:
                windows['short_term']['trades'].append(trade)
            elif dte <= 45:
                windows['medium_term']['trades'].append(trade)
            else:
                windows['long_term']['trades'].append(trade)

        # Calculate metrics for each window
        result = {}
        for window_name, window_data in windows.items():
            window_trades = window_data['trades']
            if not window_trades:
                result[window_name] = {
                    'total_trades': 0,
                    'closed_trades': 0,
                    'win_rate': 0.0,
                    'avg_roi': 0.0,
                    'total_pnl': 0.0,
                }
            else:
                win_rate, wins, closed = PerformanceService.calculate_win_rate(window_trades)
                avg_roi, _ = PerformanceService.calculate_average_roi(window_trades)
                total_pnl = PerformanceService.calculate_total_pnl(window_trades)

                result[window_name] = {
                    'total_trades': len(window_trades),
                    'closed_trades': closed,
                    'win_rate': round(win_rate, 2),
                    'avg_roi': round(avg_roi, 2),
                    'total_pnl': round(total_pnl, 2),
                }

        return result

    @staticmethod
    def analyze_by_symbol(trades: List[Dict], top_n: int = 5) -> Dict[str, Dict]:
        """
        Analyze performance by symbol (stock ticker).

        Args:
            trades: List of trade dictionaries
            top_n: Number of top performers to return

        Returns:
            Dict with analysis per symbol
        """
        symbol_groups = {}

        for trade in trades:
            symbol = trade.get('symbol', 'UNKNOWN')
            if symbol not in symbol_groups:
                symbol_groups[symbol] = []
            symbol_groups[symbol].append(trade)

        # Calculate metrics for each symbol
        result = {}
        for symbol, symbol_trades in symbol_groups.items():
            win_rate, wins, closed = PerformanceService.calculate_win_rate(symbol_trades)
            avg_roi, _ = PerformanceService.calculate_average_roi(symbol_trades)
            total_pnl = PerformanceService.calculate_total_pnl(symbol_trades)

            result[symbol] = {
                'total_trades': len(symbol_trades),
                'closed_trades': closed,
                'win_rate': round(win_rate, 2),
                'avg_roi': round(avg_roi, 2),
                'total_pnl': round(total_pnl, 2),
            }

        # Sort by total P&L and return top N
        sorted_symbols = sorted(
            result.items(),
            key=lambda x: x[1]['total_pnl'],
            reverse=True
        )

        return {
            'top_performers': dict(sorted_symbols[:top_n]),
            'all_symbols': result,
        }

    @staticmethod
    def get_monthly_performance(trades: List[Dict]) -> Dict[str, Dict]:
        """
        Break down performance by month.

        Args:
            trades: List of trade dictionaries

        Returns:
            Dict with performance metrics per month (YYYY-MM format)
        """
        monthly_groups = {}

        for trade in trades:
            entry_date = trade.get('entry_date')
            if not entry_date:
                continue

            # Parse ISO format date
            try:
                if isinstance(entry_date, str):
                    dt = datetime.fromisoformat(entry_date.replace('Z', '+00:00'))
                else:
                    dt = entry_date
                month_key = dt.strftime('%Y-%m')
            except (ValueError, AttributeError):
                continue

            if month_key not in monthly_groups:
                monthly_groups[month_key] = []
            monthly_groups[month_key].append(trade)

        # Calculate metrics for each month
        result = {}
        for month, month_trades in sorted(monthly_groups.items()):
            win_rate, wins, closed = PerformanceService.calculate_win_rate(month_trades)
            avg_roi, _ = PerformanceService.calculate_average_roi(month_trades)
            total_pnl = PerformanceService.calculate_total_pnl(month_trades)

            result[month] = {
                'total_trades': len(month_trades),
                'closed_trades': closed,
                'win_rate': round(win_rate, 2),
                'avg_roi': round(avg_roi, 2),
                'total_pnl': round(total_pnl, 2),
            }

        return result

    @staticmethod
    def get_aggregate_performance(trades: List[Dict]) -> Dict[str, any]:
        """
        Calculate aggregate performance metrics across all trades.

        Args:
            trades: List of trade dictionaries

        Returns:
            Dict with all key metrics
        """
        win_rate, wins, closed = PerformanceService.calculate_win_rate(trades)
        avg_roi, roi_count = PerformanceService.calculate_average_roi(trades)
        total_pnl = PerformanceService.calculate_total_pnl(trades)
        sharpe, sharpe_count = PerformanceService.calculate_sharpe_ratio(trades)
        max_dd, dd_count = PerformanceService.calculate_max_drawdown(trades)

        return {
            'total_trades': len(trades),
            'open_trades': len([t for t in trades if t.get('status') == 'open']),
            'closed_trades': closed,
            'win_rate_pct': round(win_rate, 2),
            'winning_trades': wins,
            'losing_trades': closed - wins if closed > 0 else 0,
            'average_roi_pct': round(avg_roi, 2),
            'total_realized_pnl': round(total_pnl, 2),
            'sharpe_ratio': round(sharpe, 4),
            'max_drawdown_pct': round(max_dd, 2),
        }
