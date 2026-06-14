"""
Central registry for all trading strategies.

Strategies register themselves with metadata and implementation class.
Scanner code retrieves strategies from registry dynamically.

This enables:
- No hardcoded strategy references in main app
- Easy to add new strategies (just register them)
- UI can list available strategies automatically
- Strategy-aware API endpoints

Design Pattern: Registry Pattern
Reference: .claude/referenced-skills/dev-patterns/
"""

from typing import Dict, Optional, Tuple, Any, Type
import logging

from scanner.base_strategy import BaseStrategy
from web.models.strategy import (
    StrategyMetadata,
    get_all_strategies,
    get_strategy_metadata,
    strategy_exists,
)

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """
    Singleton registry for all available strategies.

    Strategies are registered with metadata and their implementation class.
    Registry provides methods to:
    - Get strategy metadata (for UI, configuration)
    - Instantiate strategy objects (for scanning)
    - Validate strategy exists
    - List all available strategies
    """

    def __init__(self):
        """Initialize empty registry."""
        self._strategies: Dict[str, Tuple[StrategyMetadata, Type[BaseStrategy]]] = {}

    def register(
        self,
        metadata: StrategyMetadata,
        strategy_class: Type[BaseStrategy],
    ) -> None:
        """
        Register a strategy.

        Args:
            metadata: StrategyMetadata with strategy info
            strategy_class: Class that implements BaseStrategy

        Raises:
            ValueError: If strategy already registered or metadata/class invalid
        """
        if not metadata or not strategy_class:
            raise ValueError("Both metadata and strategy_class required")

        if metadata.id in self._strategies:
            logger.warning(
                f"Overwriting existing strategy registration: {metadata.id}"
            )

        self._strategies[metadata.id] = (metadata, strategy_class)
        logger.info(f"Registered strategy: {metadata.id} ({metadata.name})")

    def get_metadata(self, strategy_id: str) -> Optional[StrategyMetadata]:
        """
        Get metadata for a strategy.

        Args:
            strategy_id: Strategy ID (e.g., "CSP", "WHEEL")

        Returns:
            StrategyMetadata if found, None otherwise
        """
        if strategy_id not in self._strategies:
            return None
        return self._strategies[strategy_id][0]

    def get_all_metadata(self) -> Dict[str, StrategyMetadata]:
        """
        Get metadata for all registered strategies.

        Used by home screen and strategy selector UI.

        Returns:
            Dict mapping strategy_id → StrategyMetadata
        """
        return {
            strategy_id: metadata
            for strategy_id, (metadata, _) in self._strategies.items()
        }

    def get_strategy(
        self,
        strategy_id: str,
        config: Dict[str, Any],
    ) -> Optional[BaseStrategy]:
        """
        Instantiate a strategy.

        Args:
            strategy_id: Strategy ID (e.g., "CSP", "WHEEL")
            config: Configuration dict from web/config.py

        Returns:
            Strategy instance if found, None otherwise

        Raises:
            RuntimeError: If strategy class can't be instantiated
        """
        if strategy_id not in self._strategies:
            logger.error(f"Strategy not found: {strategy_id}")
            return None

        metadata, strategy_class = self._strategies[strategy_id]

        try:
            instance = strategy_class(metadata, config)
            logger.info(f"Instantiated strategy: {strategy_id}")
            return instance
        except Exception as e:
            logger.error(f"Failed to instantiate strategy {strategy_id}: {str(e)}")
            raise RuntimeError(f"Cannot instantiate strategy {strategy_id}: {str(e)}")

    def strategy_exists(self, strategy_id: str) -> bool:
        """
        Check if a strategy is registered.

        Args:
            strategy_id: Strategy ID to check

        Returns:
            True if registered, False otherwise
        """
        return strategy_id in self._strategies

    def list_strategy_ids(self) -> list[str]:
        """
        Get list of all registered strategy IDs.

        Returns:
            List of strategy IDs (e.g., ["CSP", "WHEEL"])
        """
        return list(self._strategies.keys())


# Global singleton instance
_registry = StrategyRegistry()


# Registration functions called on module import
def register_csp_strategy():
    """Register CSP strategy (called on module import)."""
    try:
        from scanner.strategies.csp_strategy import CSPStrategy
        from web.models.strategy import CSP_METADATA

        _registry.register(CSP_METADATA, CSPStrategy)
    except ImportError as e:
        logger.warning(f"Could not import CSPStrategy: {e}")


def register_wheel_strategy():
    """Register Wheel strategy (called on module import)."""
    try:
        from scanner.strategies.wheel_strategy import WheelStrategy
        from web.models.strategy import WHEEL_METADATA

        _registry.register(WHEEL_METADATA, WheelStrategy)
    except ImportError as e:
        logger.warning(f"Could not import WheelStrategy: {e}")


# Public API
def get_registry() -> StrategyRegistry:
    """Get the global strategy registry."""
    return _registry


def get_strategy_metadata(strategy_id: str) -> Optional[StrategyMetadata]:
    """Get metadata for a specific strategy."""
    return _registry.get_metadata(strategy_id)


def get_all_strategies() -> Dict[str, StrategyMetadata]:
    """Get metadata for all registered strategies."""
    return _registry.get_all_metadata()


def get_strategy(strategy_id: str, config: Dict[str, Any]) -> Optional[BaseStrategy]:
    """Instantiate a strategy."""
    return _registry.get_strategy(strategy_id, config)


def strategy_exists(strategy_id: str) -> bool:
    """Check if a strategy is registered."""
    return _registry.strategy_exists(strategy_id)
