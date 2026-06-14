"""
Trading strategies module.

Contains implementations of various trading strategies.
Each strategy implements the BaseStrategy interface.

Strategies are registered with the strategy registry on module import.
"""

# Import strategy implementations
from scanner.strategies.csp_strategy import CSPStrategy
from scanner.strategies.wheel_strategy import WheelStrategy

# Import registry and register strategies
from scanner.strategy_registry import get_registry

registry = get_registry()

# Register available strategies
try:
    from web.models.strategy import CSP_METADATA
    registry.register(CSP_METADATA, CSPStrategy)
except Exception as e:
    import logging
    logging.warning(f"Failed to register CSP strategy: {e}")

try:
    from web.models.strategy import WHEEL_METADATA
    registry.register(WHEEL_METADATA, WheelStrategy)
except Exception as e:
    import logging
    logging.warning(f"Failed to register Wheel strategy: {e}")

__all__ = [
    'CSPStrategy',
    'WheelStrategy',
]
