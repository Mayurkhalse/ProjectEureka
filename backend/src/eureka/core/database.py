"""Database engine and session management for PostgreSQL 16 using SQLAlchemy 2.0 with safe development-only fallback."""

from contextlib import asynccontextmanager, contextmanager
import logging
from pathlib import Path
from typing import AsyncGenerator, Generator
from sqlalchemy import text, create_engine
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from eureka.core.config import get_settings

logger = logging.getLogger("eureka.core.database")
settings = get_settings()

is_sync_sqlite = "sqlite" in settings.sync_database_url
is_async_sqlite = "sqlite" in settings.async_database_url

# Async Engine for FastAPI asynchronous request handlers
if is_async_sqlite:
    async_engine: AsyncEngine = create_async_engine(
        settings.async_database_url,
        echo=settings.DEBUG,
    )
else:
    async_engine: AsyncEngine = create_async_engine(
        settings.async_database_url,
        echo=settings.DEBUG,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_timeout=settings.POSTGRES_POOL_TIMEOUT,
        pool_pre_ping=True,
    )

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Sync Engine for Celery tasks, Alembic migrations, and batch workers
if is_sync_sqlite:
    sync_engine = create_engine(
        settings.sync_database_url,
        echo=settings.DEBUG,
        connect_args={"check_same_thread": False},
    )
else:
    sync_engine = create_engine(
        settings.sync_database_url,
        echo=settings.DEBUG,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_timeout=settings.POSTGRES_POOL_TIMEOUT,
        pool_pre_ping=True,
    )

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def is_sqlite_fallback_allowed() -> bool:
    """Fallback to local SQLite is ONLY permitted in local development/test/demo when explicitly allowed.
    
    Strictly prohibited in production, prod, or staging.
    """
    curr_settings = get_settings()
    env_lower = (curr_settings.ENVIRONMENT or "").strip().lower()
    if env_lower in ("production", "prod", "staging"):
        return False
    return bool(curr_settings.ALLOW_SQLITE_FALLBACK)


def _get_sqlite_fallback_path() -> Path | None:
    candidates = [
        Path("eureka_db.db"),
        Path("backend/eureka.db"),
        Path(__file__).resolve().parent.parent.parent.parent / "eureka_db.db",
        Path(__file__).resolve().parent.parent.parent.parent / "backend" / "eureka.db",
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    return None


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection generator yielding an async database session."""
    session = None
    try:
        session = AsyncSessionLocal()
        # Verify connection readiness
        await session.execute(text("SELECT 1"))
    except Exception as e:
        if session:
            try:
                await session.close()
            except Exception:
                pass

        if is_sqlite_fallback_allowed() and not is_async_sqlite:
            err_str = str(e).lower()
            is_conn_error = isinstance(e, (OperationalError, InterfaceError)) or any(
                w in err_str for w in ("connection refused", "could not connect", "timeout", "unreachable")
            )
            if is_conn_error:
                fb_path = _get_sqlite_fallback_path()
                if fb_path:
                    logger.warning("Async PostgreSQL connection unavailable (%s); routing to verified local store %s", e, fb_path)
                    fb_engine = create_async_engine(f"sqlite+aiosqlite:///{fb_path}")
                    fb_maker = async_sessionmaker(bind=fb_engine, class_=AsyncSession, autocommit=False, autoflush=False)
                    session = fb_maker()
                else:
                    raise
            else:
                raise
        else:
            # Production, staging, or fallback disabled: fail fast
            raise

    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def async_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for background workers needing an async session."""
    session = None
    try:
        session = AsyncSessionLocal()
        await session.execute(text("SELECT 1"))
    except Exception as e:
        if session:
            try:
                await session.close()
            except Exception:
                pass

        if is_sqlite_fallback_allowed() and not is_async_sqlite:
            err_str = str(e).lower()
            is_conn_error = isinstance(e, (OperationalError, InterfaceError)) or any(
                w in err_str for w in ("connection refused", "could not connect", "timeout", "unreachable")
            )
            if is_conn_error:
                fb_path = _get_sqlite_fallback_path()
                if fb_path:
                    logger.warning("Async PostgreSQL context unavailable (%s); routing to verified local store %s", e, fb_path)
                    fb_engine = create_async_engine(f"sqlite+aiosqlite:///{fb_path}")
                    fb_maker = async_sessionmaker(bind=fb_engine, class_=AsyncSession, autocommit=False, autoflush=False)
                    session = fb_maker()
                else:
                    raise
            else:
                raise
        else:
            raise

    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@contextmanager
def sync_db_context() -> Generator[Session, None, None]:
    """Synchronous context manager for Celery workers and synchronous tasks."""
    session = None
    try:
        session = SyncSessionLocal()
        session.execute(text("SELECT 1"))
    except Exception as e:
        if session:
            try:
                session.close()
            except Exception:
                pass

        if is_sqlite_fallback_allowed() and not is_sync_sqlite:
            err_str = str(e).lower()
            is_conn_error = isinstance(e, (OperationalError, InterfaceError)) or any(
                w in err_str for w in ("connection refused", "could not connect", "timeout", "unreachable")
            )
            if is_conn_error:
                fb_path = _get_sqlite_fallback_path()
                if fb_path:
                    logger.warning("Sync PostgreSQL context unavailable (%s); routing to verified local store %s", e, fb_path)
                    fb_engine = create_engine(f"sqlite:///{fb_path}", connect_args={"check_same_thread": False})
                    FbSession = sessionmaker(bind=fb_engine, autocommit=False, autoflush=False)
                    session = FbSession()
                else:
                    raise
            else:
                raise
        else:
            raise

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def check_async_db_health() -> bool:
    """Verify live PostgreSQL connectivity via asyncpg."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception:
        return False


def check_sync_db_health() -> bool:
    """Verify live primary database connectivity via psycopg2 (or configured primary engine)."""
    session = None
    try:
        session = SyncSessionLocal()
        result = session.execute(text("SELECT 1"))
        return result.scalar() == 1
    except Exception:
        return False
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass
