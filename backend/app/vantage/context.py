from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Identity derived from a verified server session, never request JSON."""

    user_id: str
    organization_id: str
    roles: frozenset[str]
    home_grants: frozenset[str] = frozenset()

    def has_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))

