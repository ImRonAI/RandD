"""Property brief tool — property row + features + standing instructions.

Credential fields are always masked with :func:`strqc_shared.crypto.mask_secret`.
Neither plaintext nor ciphertext ever leaves this tool.
"""

from __future__ import annotations

from strands import tool
from strqc_db import repositories
from strqc_shared.crypto import mask_secret

from ..context import get_context

# Columns that must never be exposed raw (ciphertext or reference).
_SECRET_COLUMNS = (
    "wifi_password_ciphertext",
    "wifi_password_secret_ref",
    "door_code_ciphertext",
    "door_code_secret_ref",
)


@tool
def get_property_brief() -> dict:
    """Summarize the active property: identity, address, features, standing instructions.

    Returns:
        Property brief with credentials masked (never plaintext or ciphertext).
    """
    ctx = get_context()
    if ctx.property_id is None:
        raise RuntimeError("no active property")
    conn = ctx.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM property WHERE property_id = ?", (ctx.property_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError(f"property {ctx.property_id} not found")
        prop = dict(row)
        features = repositories.property_features(conn, ctx.property_id)
    finally:
        conn.close()

    has_wifi_secret = bool(prop.get("wifi_password_ciphertext") or prop.get("wifi_password_secret_ref"))
    has_door_secret = bool(prop.get("door_code_ciphertext") or prop.get("door_code_secret_ref"))
    for col in _SECRET_COLUMNS:
        prop.pop(col, None)

    return {
        "unit_code": prop["unit_code"],
        "display_name": prop["display_name"],
        "address": ", ".join(
            p for p in (prop["address_line_1"], prop["city"], prop["state_province"], prop["postal_code"]) if p
        ),
        "wifi_ssid": prop["wifi_ssid"],
        "wifi_password": mask_secret("****") if has_wifi_secret else "",
        "door_code": mask_secret("****") if has_door_secret else "",
        "standing_instructions": prop["standing_instructions"] or "",
        "features": [
            {
                "feature": f["feature_name"],
                "location": f["location_label"] or "",
                "quantity": f["quantity"],
            }
            for f in features
        ],
    }
