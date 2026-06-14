"""
Strategy metadata and registry.

Defines available trading strategies and their configurations.
Each strategy is registered with metadata describing its parameters, UI labels, and behavior.

Following dev-patterns for configuration management.
"""

from enum import Enum
from typing import Optional
from dataclasses import dataclass


class StrategyType(Enum):
    """Strategy types for categorization and filtering."""
    INCOME = "income"              # Generates monthly/weekly income
    DIRECTIONAL = "directional"    # Bullish/bearish bet
    VOLATILITY = "volatility"      # Vol expansion/contraction plays


class StrategyID(Enum):
    """Available strategies - easily extensible."""
    CSP = "CSP"
    WHEEL = "WHEEL"
    CALL_SPREAD = "CALL_SPREAD"
    COVERED_CALL = "COVERED_CALL"
    LEAPS = "LEAPS"
    STRANGLE = "STRANGLE"
    IRON_CONDOR = "IRON_CONDOR"


@dataclass
class StrategyMetadata:
    """
    Immutable strategy information.

    Used by UI to render strategy cards, configure scanners,
    and adapt dashboards dynamically.
    """
    id: str                         # "CSP", "WHEEL", etc.
    name: str                       # "Cash-Secured Put"
    description: str                # "Sell puts for monthly income"
    icon: str                       # "📊" emoji for UI
    strategy_type: StrategyType     # INCOME, DIRECTIONAL, VOLATILITY
    position_type: str              # "sell" | "buy" | "spread"
    target_universe: str            # "SP500" | "NASDAQ100" | "ALL"
    recommended_dte_min: int        # 21
    recommended_dte_max: int        # 45
    recommended_delta_min: float    # -0.20 or +0.20 depending on strategy
    recommended_delta_max: float    # -0.15 or +0.80 depending on strategy
    learn_url: str                  # Link to educational resource
    color_hex: str                  # Theme color for strategy UI

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'type': self.strategy_type.value,
            'position_type': self.position_type,
            'target_universe': self.target_universe,
            'recommended_dte_min': self.recommended_dte_min,
            'recommended_dte_max': self.recommended_dte_max,
            'recommended_delta_min': self.recommended_delta_min,
            'recommended_delta_max': self.recommended_delta_max,
            'learn_url': self.learn_url,
            'color_hex': self.color_hex,
        }


# Strategy metadata definitions (used to register strategies)
CSP_METADATA = StrategyMetadata(
    id=StrategyID.CSP.value,
    name="Cash-Secured Put",
    description="Sell puts for monthly income generation",
    icon="📊",
    strategy_type=StrategyType.INCOME,
    position_type="sell",
    target_universe="SP500",
    recommended_dte_min=21,
    recommended_dte_max=45,
    recommended_delta_min=-0.30,
    recommended_delta_max=-0.10,
    learn_url="https://www.investopedia.com/terms/c/cash-secured-put.asp",
    color_hex="#22c55e",  # Green
)

WHEEL_METADATA = StrategyMetadata(
    id=StrategyID.WHEEL.value,
    name="Wheel Strategy",
    description="Sell puts → Get assigned → Sell covered calls → Repeat",
    icon="🎡",
    strategy_type=StrategyType.INCOME,
    position_type="sell",
    target_universe="SP500",
    recommended_dte_min=21,
    recommended_dte_max=45,
    recommended_delta_min=-0.30,
    recommended_delta_max=-0.10,
    learn_url="https://www.investopedia.com/terms/w/wheel.asp",
    color_hex="#f59e0b",  # Amber
)

CALL_SPREAD_METADATA = StrategyMetadata(
    id=StrategyID.CALL_SPREAD.value,
    name="Call Spread",
    description="Sell call spreads for limited-risk income",
    icon="📈",
    strategy_type=StrategyType.INCOME,
    position_type="spread",
    target_universe="SP500",
    recommended_dte_min=14,
    recommended_dte_max=45,
    recommended_delta_min=-0.30,
    recommended_delta_max=-0.10,
    learn_url="https://www.investopedia.com/terms/c/callspread.asp",
    color_hex="#3b82f6",  # Blue
)

COVERED_CALL_METADATA = StrategyMetadata(
    id=StrategyID.COVERED_CALL.value,
    name="Covered Call",
    description="Sell calls on owned stock for income",
    icon="📞",
    strategy_type=StrategyType.INCOME,
    position_type="sell",
    target_universe="SP500",
    recommended_dte_min=14,
    recommended_dte_max=45,
    recommended_delta_min=0.20,
    recommended_delta_max=0.40,
    learn_url="https://www.investopedia.com/terms/c/coveredcall.asp",
    color_hex="#06b6d4",  # Cyan
)

LEAPS_METADATA = StrategyMetadata(
    id=StrategyID.LEAPS.value,
    name="LEAPS",
    description="Buy long-dated calls for directional exposure",
    icon="🚀",
    strategy_type=StrategyType.DIRECTIONAL,
    position_type="buy",
    target_universe="SP500",
    recommended_dte_min=180,
    recommended_dte_max=730,
    recommended_delta_min=0.50,
    recommended_delta_max=0.80,
    learn_url="https://www.investopedia.com/terms/l/leaps.asp",
    color_hex="#a855f7",  # Purple
)

STRANGLE_METADATA = StrategyMetadata(
    id=StrategyID.STRANGLE.value,
    name="Strangle",
    description="Sell both calls and puts for volatility capture",
    icon="🎪",
    strategy_type=StrategyType.VOLATILITY,
    position_type="spread",
    target_universe="SP500",
    recommended_dte_min=21,
    recommended_dte_max=45,
    recommended_delta_min=-0.30,
    recommended_delta_max=0.30,
    learn_url="https://www.investopedia.com/terms/s/strangle.asp",
    color_hex="#ec4899",  # Pink
)

IRON_CONDOR_METADATA = StrategyMetadata(
    id=StrategyID.IRON_CONDOR.value,
    name="Iron Condor",
    description="Sell call and put spreads for neutral outlook",
    icon="🦅",
    strategy_type=StrategyType.VOLATILITY,
    position_type="spread",
    target_universe="SP500",
    recommended_dte_min=21,
    recommended_dte_max=45,
    recommended_delta_min=-0.30,
    recommended_delta_max=0.30,
    learn_url="https://www.investopedia.com/terms/i/ironcondor.asp",
    color_hex="#ef4444",  # Red
)

# Register available strategies (MVP includes CSP and WHEEL)
AVAILABLE_STRATEGIES = {
    StrategyID.CSP.value: CSP_METADATA,
    StrategyID.WHEEL.value: WHEEL_METADATA,
    # Future strategies (extensible):
    # StrategyID.CALL_SPREAD.value: CALL_SPREAD_METADATA,
    # StrategyID.COVERED_CALL.value: COVERED_CALL_METADATA,
    # StrategyID.LEAPS.value: LEAPS_METADATA,
    # StrategyID.STRANGLE.value: STRANGLE_METADATA,
    # StrategyID.IRON_CONDOR.value: IRON_CONDOR_METADATA,
}


def get_strategy_metadata(strategy_id: str) -> Optional[StrategyMetadata]:
    """Get metadata for a specific strategy."""
    return AVAILABLE_STRATEGIES.get(strategy_id)


def get_all_strategies() -> dict[str, StrategyMetadata]:
    """Get all available strategies."""
    return AVAILABLE_STRATEGIES.copy()


def strategy_exists(strategy_id: str) -> bool:
    """Check if a strategy is registered."""
    return strategy_id in AVAILABLE_STRATEGIES
