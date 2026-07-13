"""DAH-126 transaction-local PostgreSQL tenant-context contract.

The verified session creates ``TenantContext``. Request payload organization
identifiers never enter this module. DAH-125's PostgreSQL adapter must execute
tenant-owned statements only inside :func:`tenant_transaction`.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator
from uuid import UUID

from .context import TenantContext

SET_TRANSACTION_CONTEXT_SQL = """
SELECT
  set_config('app.org_id', %s, true),
  set_config('app.user_id', %s, true)
""".strip()


def transaction_context_values(context: TenantContext) -> tuple[str, str]:
    """Validate and return server-derived UUID values in SQL parameter order."""

    organization_id = str(UUID(context.organization_id))
    user_id = str(UUID(context.user_id))
    return organization_id, user_id


def set_transaction_context(connection: Any, context: TenantContext) -> None:
    """Install org/user GUCs locally in an already-active transaction."""

    organization_id, user_id = transaction_context_values(context)
    connection.execute(SET_TRANSACTION_CONTEXT_SQL, (organization_id, user_id))


@contextmanager
def tenant_transaction(connect: Callable[[], Any], context: TenantContext) -> Iterator[Any]:
    """Open one transaction, set context first, and expire it on exit.

    ``connect`` returns a psycopg-compatible connection whose ``transaction``
    context commits on success and rolls back on error. A pooled connection is
    returned only after that boundary has ended, so transaction-local GUCs
    cannot survive checkout reuse.
    """

    with connect() as connection:
        with connection.transaction():
            set_transaction_context(connection, context)
            yield connection
