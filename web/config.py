"""
Configuration module for CSP Scanner web application.

Follows dev-patterns: All configuration loaded from environment variables.
No hardcoded secrets, ports, or paths.

Reference: .claude/referenced-skills/dev-patterns/COMMON_GROUND.md
"""

import os
import logging
from pathlib import Path
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)


class Config:
    """Base configuration class with environment variable validation."""

    # Server Configuration
    HOST: str = os.getenv('HOST', '127.0.0.1')
    PORT: int = int(os.getenv('PORT', '5000'))
    DEBUG: bool = os.getenv('DEBUG', 'false').lower() == 'true'

    # Database Configuration
    DATABASE_PATH: str = os.getenv('DATABASE_PATH', 'data/trades.db')
    DATABASE_URL: str = f"sqlite:///{DATABASE_PATH}"

    # Alpaca API Configuration (credentials managed per-request in headers)
    ALPACA_BASE_URL: str = os.getenv(
        'ALPACA_BASE_URL',
        'https://paper-api.alpaca.markets'
    )
    ALPACA_DATA_URL: str = os.getenv(
        'ALPACA_DATA_URL',
        'https://data.alpaca.markets'
    )

    # Application Configuration
    RESULTS_DIR: str = os.getenv('RESULTS_DIR', 'outputs')
    LOGS_DIR: str = os.getenv('LOGS_DIR', 'logs')
    CACHE_DIR: str = os.getenv('CACHE_DIR', 'data/cache')

    # Flask Configuration
    SEND_FILE_MAX_AGE_DEFAULT: int = 0  # Disable caching in development
    TEMPLATES_AUTO_RELOAD: bool = True
    JSON_SORT_KEYS: bool = False

    @classmethod
    def validate(cls) -> None:
        """
        Validate that all required configuration is properly set.

        Raises:
            ValueError: If required configuration is missing or invalid
        """
        errors = []

        # Validate port is a valid integer in range
        try:
            port = int(os.getenv('PORT', '5000'))
            if port < 1 or port > 65535:
                errors.append(f"PORT must be between 1 and 65535, got {port}")
        except ValueError:
            errors.append(f"PORT must be a valid integer, got {os.getenv('PORT')}")

        # Validate database path is writable
        db_path = Path(cls.DATABASE_PATH).resolve()
        db_dir = db_path.parent
        if not db_dir.exists():
            try:
                db_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                errors.append(f"Cannot create database directory {db_dir}: {str(e)}")
        elif not os.access(db_dir, os.W_OK):
            errors.append(f"Database directory {db_dir} is not writable")

        # Validate other directories
        for dir_name, dir_path in [
            ('RESULTS_DIR', cls.RESULTS_DIR),
            ('LOGS_DIR', cls.LOGS_DIR),
            ('CACHE_DIR', cls.CACHE_DIR),
        ]:
            path = Path(dir_path).resolve()
            if not path.exists():
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    errors.append(f"Cannot create {dir_name} {path}: {str(e)}")
            elif not os.access(path, os.W_OK):
                errors.append(f"{dir_name} {path} is not writable")

        # Report all errors at once
        if errors:
            error_message = "Configuration validation failed:\n" + "\n".join(
                f"  - {error}" for error in errors
            )
            logger.error(error_message)
            raise ValueError(error_message)

        logger.info("Configuration validation passed")

    @classmethod
    def get_database_url(cls) -> str:
        """
        Get the database URL for SQLAlchemy.

        Returns:
            str: Database URL (e.g., sqlite:///data/trades.db)
        """
        return cls.DATABASE_URL

    @classmethod
    def get_alpaca_headers(cls) -> dict:
        """
        Build base headers for Alpaca API requests.
        Note: API credentials (APCA-API-KEY-ID, APCA-API-SECRET-KEY) are added per-request.

        Returns:
            dict: Standard headers for Alpaca API
        """
        return {
            'User-Agent': 'csp-scanner/1.0',
            'Content-Type': 'application/json',
        }

    def __repr__(self) -> str:
        """Return a safe string representation (no secrets)."""
        return (
            f"<Config "
            f"host={self.HOST} "
            f"port={self.PORT} "
            f"debug={self.DEBUG} "
            f"database={self.DATABASE_PATH}>"
        )


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""
    DEBUG = True
    DATABASE_PATH = ':memory:'  # In-memory SQLite for tests


def get_config() -> Config:
    """
    Get the appropriate configuration class based on environment.

    Returns:
        Config: Configuration instance

    Raises:
        ValueError: If configuration validation fails
    """
    env = os.getenv('FLASK_ENV', 'development').lower()

    config_map = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'testing': TestingConfig,
    }

    config_class = config_map.get(env, DevelopmentConfig)
    logger.info(f"Using {env.capitalize()} configuration: {config_class.__name__}")

    # Validate configuration
    config_class.validate()

    return config_class()
