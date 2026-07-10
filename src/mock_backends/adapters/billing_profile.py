"""
Mock Billing Profile Adapter — source of truth for customer billing profile
linkage (used by Spotify's billing-profile-missing scenario) and trade-in
valuation records (used by the device trade-in mismatch scenario).
Implements DataSourceAdapter contract.

Per components.md (2.11), infrastructure-design.md (Lambda: ora-adapter-billing-profile).
"""

from __future__ import annotations

from typing import Any

from mock_backends.shared.data_source_adapter import LookupResponse

# Simulated billing profile linkage — customers not in this set are treated
# as missing a billing profile (Spotify scenario 8).
_LINKED_CUSTOMERS: dict[str, str] = {}

# Simulated trade-in valuation disputes — a hard business-rule block per BR-9,
# distinct from a simple missing-billing-profile fetch failure.
_TRADE_IN_DISPUTES: set[str] = set()


def lookup(key: str) -> LookupResponse:
    """key = customer_id. Returns the linked billing_profile_id, if any."""
    if not key:
        return LookupResponse(
            success=False, key=key, value=None,
            error_type="NOT_FOUND", message="customer_id is required to look up a billing profile",
        )

    billing_profile_id = _LINKED_CUSTOMERS.get(key)
    if billing_profile_id is None:
        return LookupResponse(
            success=False, key=key, value=None,
            error_type="BILLING_PROFILE_MISSING",
            message=f"No billing profile linked for customer {key}",
        )

    return LookupResponse(
        success=True, key=key, value=billing_profile_id, error_type=None,
        message="billing_profile_id resolved",
    )


def check_trade_in_dispute(order_id: str) -> bool:
    """Returns True if this order's trade-in valuation is disputed
    (hard business-rule block, per BR-9 — not fetchable/fixable)."""
    return order_id in _TRADE_IN_DISPUTES


def link_billing_profile(customer_id: str, billing_profile_id: str) -> None:
    """Test/Demo-Mode helper."""
    _LINKED_CUSTOMERS[customer_id] = billing_profile_id


def mark_trade_in_disputed(order_id: str) -> None:
    """Test/Demo-Mode helper to deterministically force the trade-in mismatch scenario."""
    _TRADE_IN_DISPUTES.add(order_id)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    result = lookup(event.get("key", ""))
    return dict(result)
