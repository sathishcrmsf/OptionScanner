"""
Database initialization and management.

Follows dev-patterns:
- Configuration-driven database setup
- Safe connection handling
- Migration support for schema changes

Reference: .claude/referenced-skills/dev-patterns/
"""

import logging
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from web.config import get_config
from web.models.trade import Base
# Import models for their side effect: registering tables on the shared Base
# metadata so Base.metadata.create_all() below creates them too.
import web.models.market_event  # noqa: F401

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manage database initialization and session creation."""

    _engine = None
    _session_factory = None

    @classmethod
    def initialize(cls) -> None:
        """
        Initialize database engine and create all tables.

        Raises:
            SQLAlchemyError: If database initialization fails
        """
        try:
            config = get_config()
            db_url = config.get_database_url()

            logger.info(f"Initializing database: {db_url}")

            # Create engine
            cls._engine = create_engine(
                db_url,
                echo=config.DEBUG,
                connect_args={"check_same_thread": False} if "sqlite" in db_url else {}
            )

            # Create session factory
            cls._session_factory = sessionmaker(bind=cls._engine)

            # Create all tables
            Base.metadata.create_all(cls._engine)
            logger.info("Database tables created/verified")

        except SQLAlchemyError as e:
            logger.error(f"Database initialization failed: {str(e)}")
            raise ValueError(f"Failed to initialize database: {str(e)}")

    @classmethod
    def get_session(cls) -> Session:
        """
        Get a new database session.

        Returns:
            SQLAlchemy Session

        Raises:
            RuntimeError: If database not initialized
        """
        if cls._session_factory is None:
            raise RuntimeError("Database not initialized. Call DatabaseManager.initialize() first")

        return cls._session_factory()

    @classmethod
    def close_all_sessions(cls) -> None:
        """Close all database connections."""
        if cls._engine:
            cls._engine.dispose()
            logger.info("Database connections closed")

    @classmethod
    def health_check(cls) -> bool:
        """
        Check database health.

        Returns:
            True if database is healthy, False otherwise
        """
        try:
            if cls._engine is None:
                return False

            with cls._engine.connect() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return False


def init_db() -> None:
    """
    Initialize database from application startup.

    This function should be called once when the Flask app starts.
    """
    try:
        DatabaseManager.initialize()
        logger.info("Database initialization complete")
    except ValueError as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise


def get_db_session() -> Session:
    """
    Get a database session.

    Convenience function for routes to get a session.

    Returns:
        SQLAlchemy Session
    """
    return DatabaseManager.get_session()
