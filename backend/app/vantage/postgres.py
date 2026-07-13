"""PostgreSQL pool and explicit transaction unit-of-work for Vantage."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Protocol
from urllib.parse import urlparse

import psycopg
from psycopg import errors
from psycopg.rows import dict_row
from psycopg.pq import TransactionStatus
from psycopg_pool import ConnectionPool, PoolClosed, PoolTimeout

from .context import TenantContext
from .domain import ConflictError, DomainError
from .pg_repository import PostgresVantageRepository


class TransactionContextSetter(Protocol):
    """DAH-126 boundary: apply transaction-local identity before any tenant query."""

    def apply(self, connection: psycopg.Connection, context: TenantContext) -> None: ...


class PostgresSettingContextSetter:
    def apply(self, connection: psycopg.Connection, context: TenantContext) -> None:
        connection.execute("SELECT set_config('app.org_id', %s, true)", (context.organization_id,))
        connection.execute("SELECT set_config('app.user_id', %s, true)", (context.user_id,))


@dataclass(frozen=True)
class JobContext:
    organization_id: str
    actor_user_id: str
    resource_type: str
    resource_id: str

    def tenant_context(self) -> TenantContext:
        if not all((self.organization_id, self.actor_user_id, self.resource_type, self.resource_id)):
            raise DomainError("invalid_job_context", "A persisted organization, actor, and resource are required")
        return TenantContext(self.actor_user_id, self.organization_id, frozenset({"SYSTEM_JOB"}), frozenset())


@dataclass(frozen=True)
class PostgresConfig:
    database_url: str
    environment: str
    min_size: int
    max_size: int
    checkout_timeout_seconds: float
    connect_timeout_seconds: int
    statement_timeout_ms: int
    lock_timeout_ms: int
    idle_transaction_timeout_ms: int
    max_waiting: int
    application_name: str

    @classmethod
    def from_env(cls) -> "PostgresConfig":
        env = os.getenv("VANTAGE_ENV", "local").strip().lower()
        url = os.getenv("DATABASE_URL", "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"postgres", "postgresql"}:
            if os.getenv("VANTAGE_ALLOW_SQLITE_TESTS") == "1" and env == "test":
                raise DomainError("isolated_sqlite_only", "SQLite test mode must construct its repository fixture directly")
            raise DomainError("postgres_required", "DATABASE_URL must be a PostgreSQL URI")
        if env in {"ci", "staging", "production"} and not os.getenv("VANTAGE_PG_POOL_MAX"):
            raise DomainError("pool_budget_required", "VANTAGE_PG_POOL_MAX is required outside local development")
        if env in {"staging", "production"} and "sslmode=" not in url:
            raise DomainError("postgres_tls_required", "DATABASE_URL must declare sslmode outside local/CI")
        min_size = int(os.getenv("VANTAGE_PG_POOL_MIN", "1"))
        max_size = int(os.getenv("VANTAGE_PG_POOL_MAX", "4"))
        if min_size < 0 or max_size < 1 or min_size > max_size:
            raise DomainError("invalid_pool_budget", "PostgreSQL pool min/max is invalid")
        return cls(
            database_url=url, environment=env, min_size=min_size, max_size=max_size,
            checkout_timeout_seconds=float(os.getenv("VANTAGE_PG_CHECKOUT_TIMEOUT_SECONDS", "2")),
            connect_timeout_seconds=int(os.getenv("VANTAGE_PG_CONNECT_TIMEOUT_SECONDS", "5")),
            statement_timeout_ms=int(os.getenv("VANTAGE_PG_STATEMENT_TIMEOUT_MS", "10000")),
            lock_timeout_ms=int(os.getenv("VANTAGE_PG_LOCK_TIMEOUT_MS", "2000")),
            idle_transaction_timeout_ms=int(os.getenv("VANTAGE_PG_IDLE_TRANSACTION_TIMEOUT_MS", "15000")),
            max_waiting=int(os.getenv("VANTAGE_PG_MAX_WAITING", str(max_size * 2))),
            application_name=os.getenv("VANTAGE_PG_APPLICATION_NAME", f"vantage-{env}"),
        )


def map_postgres_error(exc: BaseException) -> DomainError:
    if isinstance(exc, DomainError):
        return exc
    if isinstance(exc, (PoolTimeout, PoolClosed, psycopg.OperationalError)):
        return DomainError("database_unavailable", "The database is temporarily unavailable", retryable=True)
    if isinstance(exc, errors.UniqueViolation):
        return ConflictError("constraint_conflict", "The operation conflicts with an existing record")
    if isinstance(exc, (errors.ForeignKeyViolation, errors.CheckViolation, errors.NotNullViolation)):
        return DomainError("relationship_invalid", "A referenced record or value is invalid")
    if isinstance(exc, (errors.SerializationFailure, errors.DeadlockDetected)):
        return ConflictError("transaction_retry", "The transaction must be retried", retryable=True)
    if isinstance(exc, (errors.QueryCanceled, errors.LockNotAvailable, TimeoutError)):
        return DomainError("database_timeout", "The database operation timed out", retryable=True)
    if isinstance(exc, psycopg.ProgrammingError):
        return DomainError("database_contract_error", "The database contract is unavailable")
    return DomainError("database_error", "The database operation failed")


class PostgresAdapter:
    def __init__(self, config: PostgresConfig, *, context_setter: TransactionContextSetter | None = None):
        self.config = config
        self.context_setter = context_setter or PostgresSettingContextSetter()
        self.pool = ConnectionPool(
            conninfo=config.database_url,
            min_size=config.min_size,
            max_size=config.max_size,
            timeout=config.checkout_timeout_seconds,
            max_waiting=config.max_waiting,
            open=False,
            check=ConnectionPool.check_connection,
            reset=self._reset,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
                "connect_timeout": config.connect_timeout_seconds,
                "application_name": config.application_name,
            },
            name="vantage",
        )

    @staticmethod
    def _reset(connection: psycopg.Connection) -> None:
        if connection.info.transaction_status != TransactionStatus.IDLE:
            connection.rollback()
        connection.execute("RESET ALL")

    def open(self, *, wait: bool = True) -> None:
        self.pool.open(wait=wait, timeout=self.config.connect_timeout_seconds)

    def close(self, *, timeout: float = 5.0) -> None:
        self.pool.close(timeout=timeout)

    @contextmanager
    def transaction(self, context: TenantContext) -> Iterator[PostgresVantageRepository]:
        if not context.organization_id or not context.user_id:
            raise DomainError("tenant_context_required", "Verified organization and user context are required")
        try:
            with self.pool.connection(timeout=self.config.checkout_timeout_seconds) as connection:
                with connection.transaction():
                    self._set_timeouts(connection)
                    self.context_setter.apply(connection, context)
                    yield PostgresVantageRepository(connection)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise map_postgres_error(exc) from exc

    @contextmanager
    def read_only_transaction(self, context: TenantContext) -> Iterator[PostgresVantageRepository]:
        try:
            with self.pool.connection(timeout=self.config.checkout_timeout_seconds) as connection:
                with connection.transaction():
                    connection.execute("SET TRANSACTION READ ONLY")
                    self._set_timeouts(connection)
                    self.context_setter.apply(connection, context)
                    yield PostgresVantageRepository(connection)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise map_postgres_error(exc) from exc

    @contextmanager
    def auth_bootstrap_transaction(self) -> Iterator[PostgresVantageRepository]:
        """Narrow non-tenant transaction; callers may only use auth/bootstrap methods."""
        try:
            with self.pool.connection(timeout=self.config.checkout_timeout_seconds) as connection:
                with connection.transaction():
                    self._set_timeouts(connection)
                    yield PostgresVantageRepository(connection)
        except BaseException as exc:
            raise map_postgres_error(exc) from exc

    @contextmanager
    def system_job_transaction(self, job: JobContext) -> Iterator[PostgresVantageRepository]:
        # Resource reauthorization is deliberately repository/domain work inside
        # this transaction; DAH-126 supplies the role/policy implementation.
        with self.transaction(job.tenant_context()) as repository:
            yield repository

    def _set_timeouts(self, connection: psycopg.Connection) -> None:
        for name, value in (
            ("statement_timeout", self.config.statement_timeout_ms),
            ("lock_timeout", self.config.lock_timeout_ms),
            ("idle_in_transaction_session_timeout", self.config.idle_transaction_timeout_ms),
        ):
            connection.execute("SELECT set_config(%s, %s, true)", (name, str(value)))

    def health(self) -> dict[str, object]:
        stats = self.pool.get_stats()
        try:
            with self.pool.connection(timeout=self.config.checkout_timeout_seconds) as connection:
                value = connection.execute("SELECT 1 AS healthy").fetchone()
            ready = bool(value and value["healthy"] == 1)
        except Exception:
            ready = False
        return {"ready": ready, "pool": {key: stats[key] for key in (
            "pool_size", "pool_available", "requests_waiting", "requests_errors", "requests_num"
        ) if key in stats}}

    def compatibility_connection(self) -> "CompatibilityConnection":
        """Temporary DB-API bridge for auth/day services pending their typed repositories.

        The bridge still uses one explicit pool checkout and transaction. New
        business repositories must use ``transaction()`` instead.
        """
        return CompatibilityConnection(self)


class CompatibilityRow(dict[str, object]):
    def __getitem__(self, key: object) -> object:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)  # type: ignore[arg-type]


class CompatibilityCursor:
    def __init__(self, cursor: psycopg.Cursor):
        self.cursor = cursor

    @property
    def rowcount(self) -> int:
        return self.cursor.rowcount

    def fetchone(self) -> CompatibilityRow | None:
        row = self.cursor.fetchone()
        return CompatibilityRow(row) if row is not None else None

    def fetchall(self) -> list[CompatibilityRow]:
        return [CompatibilityRow(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class CompatibilityConnection:
    row_factory = None

    def __init__(self, adapter: PostgresAdapter):
        self.adapter = adapter
        self._connection_context = None
        self._transaction_context = None
        self.connection = None

    def __enter__(self) -> "CompatibilityConnection":
        self._connection_context = self.adapter.pool.connection(timeout=self.adapter.config.checkout_timeout_seconds)
        self.connection = self._connection_context.__enter__()
        self._transaction_context = self.connection.transaction()
        self._transaction_context.__enter__()
        self.adapter._set_timeouts(self.connection)
        return self

    def __exit__(self, exc_type, exc, tb):
        assert self._transaction_context is not None and self._connection_context is not None
        transaction_result = self._transaction_context.__exit__(exc_type, exc, tb)
        pool_result = self._connection_context.__exit__(exc_type, exc, tb)
        return transaction_result or pool_result

    def execute(self, query: str, params: tuple[object, ...] = ()) -> CompatibilityCursor:
        assert self.connection is not None
        # This bridge only supports the existing fixed queries, never caller SQL.
        translated = query.replace("?", "%s").replace("active=1", "active=true")
        return CompatibilityCursor(self.connection.execute(translated, params))
