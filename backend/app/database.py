"""
Production-hardened database configuration and session management.

FIXES APPLIED:
1. Added wait_for_db() with exponential backoff retry logic
2. Fixed session leak in get_db() (was creating a throwaway session for logging)
3. init_db() now calls wait_for_db() before create_all()
4. All connection attempts use proper timeout and retry semantics
"""
import os
import time
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from app.config import (
    DATABASE_URL,
    DB_POOL_SIZE,
    DB_MAX_OVERFLOW,
    DB_POOL_TIMEOUT,
    DB_POOL_RECYCLE,
    IS_PRODUCTION,
)

logger = logging.getLogger(__name__)

# ============================================================================
# ENGINE CONFIGURATION
# ============================================================================

# Create engine with production-optimized settings
engine = create_engine(
    DATABASE_URL,
    # Connection validation
    pool_pre_ping=True,  # Test connection before use
    pool_recycle=DB_POOL_RECYCLE,  # Prevent stale connections

    # Pool sizing
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,

    # Debugging
    echo=False,
    echo_pool=False,

    # Pool class
    poolclass=QueuePool,

    # Connection options — short connect timeout so retries cycle quickly
    connect_args={
        "connect_timeout": 5,
    },
)

# ============================================================================
# SESSION FACTORY
# ============================================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # Prevent lazy-load issues after commit
    class_=Session,
)

# ============================================================================
# DATABASE STARTUP — RETRY WITH EXPONENTIAL BACKOFF
# ============================================================================

def wait_for_db(max_retries: int = 5, initial_delay: float = 2.0) -> None:
    """
    Wait for the database to become available using exponential backoff.

    This is the KEY fix for the Docker race condition. Even though
    docker-compose depends_on + healthcheck ensures MySQL is "up",
    the user/database may not be fully initialised yet on first boot.

    Args:
        max_retries: Maximum number of connection attempts (default 5 → ~62s total)
        initial_delay: Seconds to wait before first retry (doubles each attempt)
    """
    delay = initial_delay
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Waiting for database (attempt {attempt}/{max_retries})...")
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info(f"Database connection established after {attempt} attempt(s)")
            return
        except OperationalError as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Database not ready (attempt {attempt}/{max_retries}): {e}. "
                    f"Retrying in {delay:.0f}s..."
                )
                time.sleep(delay)
                delay = min(delay * 2, 30)  # Cap at 30 seconds
            else:
                logger.critical(
                    f"Could not connect to database after {max_retries} attempts"
                )
        except Exception as e:
            last_error = e
            logger.error(f"Unexpected error connecting to database: {e}")
            if attempt >= max_retries:
                break
            time.sleep(delay)
            delay = min(delay * 2, 30)

    raise RuntimeError(
        f"Database unavailable after {max_retries} attempts. Last error: {last_error}"
    )


# ============================================================================
# FASTAPI DEPENDENCY
# ============================================================================

def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency for FastAPI routes.

    Usage:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            ...

    FIX: Removed the leaked throwaway session that was created just for logging.
    """
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database error in session: {e}")
        db.rollback()
        raise
    finally:
        db.close()


# ============================================================================
# BACKGROUND TASK CONTEXT MANAGER
# ============================================================================

@contextmanager
def get_db_context():
    """
    Context manager for background tasks and non-FastAPI usage.

    CRITICAL: Background tasks MUST use this instead of get_db()
    to create their own independent session.

    Usage:
        with get_db_context() as db:
            db.add(obj)
            # Commits automatically on success
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in background session: {e}", exc_info=True)
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error in background session: {e}", exc_info=True)
        raise
    finally:
        db.close()


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_db() -> None:
    """
    Initialize database tables.

    Calls wait_for_db() first to ensure connectivity.
    If USE_ALEMBIC_MIGRATIONS=true, table creation is managed by Alembic.
    """
    # Step 1: ensure the database is reachable
    wait_for_db()

    use_migrations = os.getenv("USE_ALEMBIC_MIGRATIONS", "false").lower() == "true"
    if use_migrations:
        logger.info("Migration mode enabled - run 'alembic upgrade head' manually")
        logger.warning("Tables will NOT be auto-created. Use Alembic migrations.")
        return

    # Step 2: create tables directly (development mode)
    try:
        from app.models import Base

        logger.info("Creating database tables directly (development mode)")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized")

        # Log table names
        table_names = list(Base.metadata.tables.keys())
        logger.info(f"Created/verified tables: {', '.join(table_names)}")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}", exc_info=True)
        raise


# ============================================================================
# HEALTH CHECK
# ============================================================================

def check_database_health() -> bool:
    """
    Check database connectivity and health.

    Returns:
        True if database is healthy, False otherwise
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        return True
    except OperationalError as e:
        logger.error(f"Database health check failed (operational): {e}")
        return False
    except Exception as e:
        logger.error(f"Database health check failed (unexpected): {e}")
        return False


# ============================================================================
# CONNECTION POOL MONITORING
# ============================================================================

@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Log new database connections."""
    logger.debug("New database connection established")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """Log connection checkout from pool."""
    logger.debug("Database connection checked out from pool")


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_conn, connection_record):
    """Log connection return to pool."""
    logger.debug("Database connection returned to pool")


def get_pool_status() -> dict:
    """
    Get current connection pool statistics.

    Returns:
        Dictionary with pool metrics
    """
    pool = engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "total": pool.size() + pool.overflow(),
    }


# ============================================================================
# GRACEFUL SHUTDOWN
# ============================================================================

def dispose_engine() -> None:
    """
    Gracefully dispose of the database engine and connection pool.
    """
    logger.info("Disposing database engine and connection pool...")
    engine.dispose()
    logger.info("Database engine disposed successfully")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "engine",
    "SessionLocal",
    "get_db",
    "get_db_context",
    "init_db",
    "wait_for_db",
    "check_database_health",
    "get_pool_status",
    "dispose_engine",
]
