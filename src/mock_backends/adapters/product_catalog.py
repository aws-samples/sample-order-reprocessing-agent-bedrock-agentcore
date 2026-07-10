"""
Mock Product Catalog Adapter — source of truth for plan_id values.
Implements DataSourceAdapter contract.

Per components.md (2.3), infrastructure-design.md (Lambda: ora-adapter-product-catalog).
"""

from __future__ import annotations

from typing import Any

from mock_backends.shared.data_source_adapter import LookupResponse

_KNOWN_PLANS = {
    "postpaid-5g-unlimited": "POST5G999",
    "postpaid-5g-50gb": "POST5G050",
    "prepaid-basic": "PRE0BASIC",
}


def lookup(key: str) -> LookupResponse:
    """key = a plan slug/customer selection; resolves to the internal plan_id."""
    plan_id = _KNOWN_PLANS.get(key)
    if plan_id is None:
        # Fall back to a generated plan_id if an unrecognized slug is provided,
        # rather than failing outright — keeps the mock forgiving for demo purposes.
        plan_id = f"PLAN-{abs(hash(key)) % 100000:05d}"

    return LookupResponse(
        success=True, key=key, value=plan_id, error_type=None,
        message="plan_id resolved from Product Catalog DB",
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    result = lookup(event.get("key", ""))
    return dict(result)
