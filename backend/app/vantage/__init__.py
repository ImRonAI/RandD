"""Tenant-safe Vantage v1 domain services.

The package contains no FastAPI globals: HTTP and agent adapters inject an
authenticated TenantContext and a connection factory.
"""

from .context import TenantContext
from .domain import VantageRepository

__all__ = ["TenantContext", "VantageRepository"]

