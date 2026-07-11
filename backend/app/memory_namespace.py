"""Server-derived, tenant-safe memory namespace construction."""

from app.evidence_storage import _safe


def memory_namespace(org_id: str, portfolio_id: str, home_id: str) -> str:
    return (
        f"orgs/{_safe(org_id, 'org_id')}/portfolios/"
        f"{_safe(portfolio_id, 'portfolio_id')}/homes/{_safe(home_id, 'home_id')}"
    )


def memory_metadata_filter(org_id: str, portfolio_id: str, home_id: str) -> dict:
    """Filter values must be supplied by verified server context, never the model."""
    return {"andAll": [
        {"equals": {"key": "org_id", "value": _safe(org_id, "org_id")}},
        {"equals": {"key": "portfolio_id", "value": _safe(portfolio_id, "portfolio_id")}},
        {"equals": {"key": "home_id", "value": _safe(home_id, "home_id")}},
    ]}

