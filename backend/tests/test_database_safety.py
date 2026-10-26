"""Regression tests verifying database fallback safety and fail-fast guarantees.

Covers the 7 mandatory pre-merge verification criteria:
1. Development with fallback disabled fails safely on connection errors.
2. Development with fallback explicitly enabled permits SQLite fallback.
3. Production with fallback disabled fails fast without routing to SQLite.
4. Production with fallback requested is strictly rejected at config validation.
5. Staging with fallback requested is strictly rejected at config validation.
6. PostgreSQL outage does not silently redirect production writes to SQLite.
7. PostgreSQL recovery does not expose or read divergent local SQLite data.
8. Non-connection errors (schema, syntax, auth) are never swallowed by fallback logic.
"""

import os
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError

from eureka.core.config import Settings, get_settings
from eureka.core.database import (
    check_sync_db_health,
    is_sqlite_fallback_allowed,
    sync_db_context,
)


@pytest.fixture(autouse=True)
def clean_settings_cache():
    """Ensure settings cache is cleared before and after each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- 1. Development with fallback disabled ---

def test_development_fallback_disabled(monkeypatch):
    """In development with ALLOW_SQLITE_FALLBACK=False, connection errors must fail fast."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_SQLITE_FALLBACK", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid_user:invalid_pass@127.0.0.1:54399/nonexistent")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.ALLOW_SQLITE_FALLBACK is False
    assert is_sqlite_fallback_allowed() is False

    # Mock SyncSessionLocal to simulate unreachable PostgreSQL
    with patch("eureka.core.database.SyncSessionLocal") as mock_session_maker:
        mock_session = MagicMock()
        mock_session.execute.side_effect = OperationalError("connection refused", {}, None)
        mock_session_maker.return_value = mock_session

        with pytest.raises(OperationalError) as exc_info:
            with sync_db_context():
                pass
        assert "connection refused" in str(exc_info.value).lower()


# --- 2. Development with fallback explicitly enabled ---

def test_development_fallback_explicitly_enabled(monkeypatch, tmp_path):
    """In development with ALLOW_SQLITE_FALLBACK=True, connection errors route to SQLite."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_SQLITE_FALLBACK", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid_user:invalid_pass@127.0.0.1:54399/nonexistent")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.ALLOW_SQLITE_FALLBACK is True
    assert is_sqlite_fallback_allowed() is True

    # Provide a temporary SQLite database file for fallback
    test_db = tmp_path / "test_fallback.db"
    test_db.touch()

    with patch("eureka.core.database._get_sqlite_fallback_path", return_value=test_db):
        with patch("eureka.core.database.SyncSessionLocal") as mock_session_maker:
            mock_session = MagicMock()
            mock_session.execute.side_effect = OperationalError("connection refused", {}, None)
            mock_session_maker.return_value = mock_session

            # Should successfully fall back to SQLite without raising OperationalError
            with sync_db_context() as session:
                assert session is not None
                # Verify session dialect is sqlite
                assert session.bind.dialect.name == "sqlite"


# --- 3. Production with fallback disabled ---

def test_production_fallback_disabled(monkeypatch):
    """In production with ALLOW_SQLITE_FALLBACK=False, settings validate and fallback is prohibited."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_SQLITE_FALLBACK", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod_user:prod_pass@10.0.0.1:5432/prod_db")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.ENVIRONMENT == "production"
    assert settings.ALLOW_SQLITE_FALLBACK is False
    assert is_sqlite_fallback_allowed() is False

    with patch("eureka.core.database.SyncSessionLocal") as mock_session_maker:
        mock_session = MagicMock()
        mock_session.execute.side_effect = OperationalError("production db unreachable", {}, None)
        mock_session_maker.return_value = mock_session

        with pytest.raises(OperationalError) as exc_info:
            with sync_db_context():
                pass
        assert "production db unreachable" in str(exc_info.value).lower()


# --- 4. Production with fallback requested and rejected ---

def test_production_fallback_requested_and_rejected():
    """Attempting ALLOW_SQLITE_FALLBACK=True in production must raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT="production", ALLOW_SQLITE_FALLBACK=True)
    assert "ALLOW_SQLITE_FALLBACK is strictly prohibited" in str(exc_info.value)

    # Also test 'prod' alias
    with pytest.raises(ValidationError) as exc_info_alias:
        Settings(ENVIRONMENT="prod", ALLOW_SQLITE_FALLBACK=True)
    assert "ALLOW_SQLITE_FALLBACK is strictly prohibited" in str(exc_info_alias.value)


# --- 5. Staging with fallback requested and rejected ---

def test_staging_fallback_requested_and_rejected():
    """Attempting ALLOW_SQLITE_FALLBACK=True in staging must raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT="staging", ALLOW_SQLITE_FALLBACK=True)
    assert "ALLOW_SQLITE_FALLBACK is strictly prohibited" in str(exc_info.value)


# --- 6. PostgreSQL outage does not redirect production writes ---

def test_postgresql_outage_does_not_redirect_production_writes(monkeypatch, tmp_path):
    """During a PostgreSQL outage in production, writes must fail immediately and not divert to SQLite."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_SQLITE_FALLBACK", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod_user:prod_pass@10.0.0.1:5432/prod_db")
    get_settings.cache_clear()

    # Pre-create an empty SQLite file to ensure it is NOT written to
    canary_sqlite = tmp_path / "divergent_canary.db"
    canary_sqlite.touch()
    initial_size = canary_sqlite.stat().st_size

    with patch("eureka.core.database._get_sqlite_fallback_path", return_value=canary_sqlite):
        with patch("eureka.core.database.SyncSessionLocal") as mock_session_maker:
            mock_session = MagicMock()
            mock_session.execute.side_effect = OperationalError("PostgreSQL cluster network partition", {}, None)
            mock_session_maker.return_value = mock_session

            # The write attempt must fail fast
            with pytest.raises(OperationalError) as exc_info:
                with sync_db_context() as session:
                    session.execute(text("INSERT INTO fact_check_tickets (id) VALUES ('fake')"))

            assert "network partition" in str(exc_info.value).lower()

    # Verify canary SQLite file was NOT modified or written to
    assert canary_sqlite.stat().st_size == initial_size


# --- 7. PostgreSQL recovery does not expose divergent SQLite data ---

def test_postgresql_recovery_does_not_expose_divergent_sqlite_data(monkeypatch, tmp_path):
    """When PostgreSQL recovers in production, sessions connect exclusively to PostgreSQL, ignoring local SQLite."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_SQLITE_FALLBACK", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod_user:prod_pass@10.0.0.1:5432/prod_db")
    get_settings.cache_clear()

    # Mock healthy recovered PostgreSQL session
    mock_pg_session = MagicMock()
    mock_pg_session.bind.dialect.name = "postgresql"
    mock_pg_session.execute.return_value.fetchall.return_value = [("canonical_pg_data",)]

    with patch("eureka.core.database.SyncSessionLocal", return_value=mock_pg_session):
        with sync_db_context() as session:
            assert session.bind.dialect.name == "postgresql"
            rows = session.execute(text("SELECT * FROM canonical_events")).fetchall()
            assert rows == [("canonical_pg_data",)]

    # is_sqlite_fallback_allowed remains False in production at all times
    assert is_sqlite_fallback_allowed() is False


# --- 8. Non-connection errors not swallowed by fallback logic ---

def test_non_connection_errors_not_swallowed(monkeypatch):
    """In development even with fallback enabled, syntax/schema/programming errors must NOT route to SQLite."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_SQLITE_FALLBACK", "true")
    get_settings.cache_clear()

    assert is_sqlite_fallback_allowed() is True

    with patch("eureka.core.database.SyncSessionLocal") as mock_session_maker:
        mock_session = MagicMock()
        # Simulate a syntax error or missing table error (ProgrammingError)
        mock_session.execute.side_effect = ProgrammingError("SELECT * FROM non_existent_table", {}, None)
        mock_session_maker.return_value = mock_session

        with pytest.raises(ProgrammingError) as exc_info:
            with sync_db_context():
                pass
        assert "non_existent_table" in str(exc_info.value)


# --- 9. Production & Staging reject SQLite DATABASE_URL ---

def test_production_rejects_sqlite_database_url():
    """In production, prod, or staging, primary SQLite DATABASE_URL is strictly prohibited."""
    for env in ("production", "prod", "staging"):
        for sqlite_url in ("sqlite:///eureka.db", "sqlite://", "sqlite+aiosqlite:///prod.db"):
            with pytest.raises(ValidationError) as exc_info:
                Settings(ENVIRONMENT=env, DATABASE_URL=sqlite_url)
            assert "strictly prohibited" in str(exc_info.value)
            assert "PostgreSQL" in str(exc_info.value)


def test_unsupported_database_url_scheme_rejected():
    """Unsupported database schemes in DATABASE_URL must raise ValidationError."""
    for scheme_url in ("mysql://root:pass@localhost/db", "oracle://scott:tiger@localhost/db", "http://example.com"):
        with pytest.raises(ValidationError) as exc_info:
            Settings(ENVIRONMENT="development", DATABASE_URL=scheme_url)
        assert "Unsupported database scheme" in str(exc_info.value)


def test_sqlite_database_url_in_allowed_environments():
    """SQLite DATABASE_URL is only permitted in explicit development/test/demo/local environments."""
    for env in ("development", "dev", "test", "demo", "local"):
        s = Settings(ENVIRONMENT=env, DATABASE_URL="sqlite:///allowed.db")
        assert s.DATABASE_URL == "sqlite:///allowed.db"

    # Any unknown or non-whitelisted environment must reject SQLite
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT="unrecognized_env", DATABASE_URL="sqlite:///unrecognized.db")
    assert "not permitted" in str(exc_info.value)


def test_production_accepts_valid_postgresql_database_url():
    """Production accepts valid PostgreSQL URLs with standard or driver-specific schemes."""
    for pg_url in (
        "postgresql://prod_user:prod_pass@10.0.0.1:5432/eureka_db",
        "postgresql+asyncpg://prod_user:prod_pass@10.0.0.1:5432/eureka_db",
        "postgresql+psycopg2://prod_user:prod_pass@10.0.0.1:5432/eureka_db",
    ):
        s = Settings(ENVIRONMENT="production", DATABASE_URL=pg_url)
        assert s.ENVIRONMENT == "production"


# --- 10. Database URL Driver Translation ---

def test_database_url_driver_translation():
    """Verifies bidirectional translation between async and sync driver schemes."""
    # 1. Bare postgresql://
    s1 = Settings(DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/testdb")
    assert s1.sync_database_url == "postgresql+psycopg2://user:pass@127.0.0.1:5432/testdb"
    assert s1.async_database_url == "postgresql+asyncpg://user:pass@127.0.0.1:5432/testdb"

    # 2. postgresql+asyncpg:// translates to +psycopg2 for sync
    s2 = Settings(DATABASE_URL="postgresql+asyncpg://user:pass@127.0.0.1:5432/testdb")
    assert s2.sync_database_url == "postgresql+psycopg2://user:pass@127.0.0.1:5432/testdb"
    assert s2.async_database_url == "postgresql+asyncpg://user:pass@127.0.0.1:5432/testdb"

    # 3. postgresql+psycopg2:// translates to +asyncpg for async
    s3 = Settings(DATABASE_URL="postgresql+psycopg2://user:pass@127.0.0.1:5432/testdb")
    assert s3.sync_database_url == "postgresql+psycopg2://user:pass@127.0.0.1:5432/testdb"
    assert s3.async_database_url == "postgresql+asyncpg://user:pass@127.0.0.1:5432/testdb"

    # 4. Bare sqlite:///
    s4 = Settings(ENVIRONMENT="test", DATABASE_URL="sqlite:///eureka.db")
    assert s4.sync_database_url == "sqlite:///eureka.db"
    assert s4.async_database_url == "sqlite+aiosqlite:///eureka.db"

    # 5. sqlite+aiosqlite:/// cleans +aiosqlite for sync
    s5 = Settings(ENVIRONMENT="test", DATABASE_URL="sqlite+aiosqlite:///eureka.db")
    assert s5.sync_database_url == "sqlite:///eureka.db"
    assert s5.async_database_url == "sqlite+aiosqlite:///eureka.db"


# --- 11. Synchronous health-check correctness ---

def test_check_sync_db_health_fails_during_postgres_outage_despite_dev_fallback(monkeypatch):
    """In development with fallback enabled, check_sync_db_health must report False if PostgreSQL is unreachable."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_SQLITE_FALLBACK", "true")
    get_settings.cache_clear()

    assert is_sqlite_fallback_allowed() is True

    # Simulate unreachable primary PostgreSQL database on SyncSessionLocal
    with patch("eureka.core.database.SyncSessionLocal") as mock_session_maker:
        mock_session_maker.side_effect = OperationalError("connection to postgres:5432 failed", {}, None)

        # Health check must verify the PRIMARY engine and NOT mask the failure with SQLite
        is_healthy = check_sync_db_health()
        assert is_healthy is False


def test_check_sync_db_health_success_when_postgres_healthy():
    """When PostgreSQL is healthy, check_sync_db_health returns True."""
    with patch("eureka.core.database.SyncSessionLocal") as mock_session_maker:
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 1
        mock_session_maker.return_value = mock_session

        assert check_sync_db_health() is True
        mock_session.close.assert_called_once()
