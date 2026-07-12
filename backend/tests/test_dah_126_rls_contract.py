from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from app.vantage.context import TenantContext
from app.vantage.rls import (
    SET_TRANSACTION_CONTEXT_SQL,
    set_transaction_context,
    tenant_transaction,
    transaction_context_values,
)


ORG = "00000000-0000-0000-0000-000000000001"
USER = "00000000-0000-0000-0000-000000000011"


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, str]]] = []
        self.transaction_entered = False
        self.transaction_exited = False
        self.connection_exited = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.connection_exited = True

    @contextmanager
    def transaction(self):
        self.transaction_entered = True
        try:
            yield
        finally:
            self.transaction_exited = True

    def execute(self, sql, values):
        assert self.transaction_entered and not self.transaction_exited
        self.calls.append((sql, values))


def _context() -> TenantContext:
    return TenantContext(USER, ORG, frozenset({"INSPECTOR"}))


def test_context_sql_is_parameterized_and_transaction_local() -> None:
    assert SET_TRANSACTION_CONTEXT_SQL.count("set_config") == 2
    assert SET_TRANSACTION_CONTEXT_SQL.count("%s") == 2
    assert "app.org_id" in SET_TRANSACTION_CONTEXT_SQL
    assert "app.user_id" in SET_TRANSACTION_CONTEXT_SQL
    assert SET_TRANSACTION_CONTEXT_SQL.count("true") == 2
    assert "SET app." not in SET_TRANSACTION_CONTEXT_SQL


def test_context_values_require_valid_server_identity_uuids() -> None:
    assert transaction_context_values(_context()) == (ORG, USER)
    with pytest.raises(ValueError):
        transaction_context_values(TenantContext("spoof", ORG, frozenset()))
    with pytest.raises(ValueError):
        transaction_context_values(TenantContext(USER, "payload-org", frozenset()))


def test_tenant_transaction_sets_context_once_before_work_and_expires_boundary() -> None:
    connection = FakeConnection()
    with tenant_transaction(lambda: connection, _context()) as scoped:
        assert scoped is connection
        assert connection.calls == [(SET_TRANSACTION_CONTEXT_SQL, (ORG, USER))]
        assert not connection.transaction_exited
    assert connection.transaction_exited and connection.connection_exited


def test_set_context_requires_active_transaction_contract() -> None:
    connection = FakeConnection()
    with pytest.raises(AssertionError):
        set_transaction_context(connection, _context())


def test_migration_freezes_roles_policies_and_auth_bootstrap_surface() -> None:
    root = Path(__file__).resolve().parents[2]
    sql = (root / "backend/migrations/0003_dah_126_roles_and_rls.sql").read_text()
    assert "ALTER ROLE vantage_runtime NOSUPERUSER" in sql
    assert "NOBYPASSRLS" in sql
    assert "ALTER TABLE public.%I FORCE ROW LEVEL SECURITY" in sql
    assert "FOR SELECT USING" in sql
    assert "FOR INSERT WITH CHECK" in sql
    assert "FOR UPDATE USING" in sql and "WITH CHECK" in sql
    assert "FOR DELETE USING" in sql
    assert "app_user_id() IS NOT NULL" in sql
    assert "SECURITY DEFINER SET search_path=pg_catalog" in sql
    assert "GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.home TO vantage_auth_bootstrap" not in sql
