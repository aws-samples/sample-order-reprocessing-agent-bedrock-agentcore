"""
FetchMissingData tool — retrieves a specific missing field's value from the
correct backend source, one call per missing field (BR-15).

Per components.md (1.3), business-logic-model.md step [4]. Handles
BACKEND_ERROR retry-once logic (business-logic-model.md's Retry Behavior
section).
"""

from __future__ import annotations

from typing import Any

from agent.shared.tool_types import FetchResult
from mock_backends.adapters import (
    billing_profile,
    device_inventory,
    disneyplus,
    esim_provisioning,
    imei_registry,
    netflix,
    number_portability,
    product_catalog,
    sim_inventory,
    spotify,
)
from mock_backends.repository import history_repository
from mock_backends.shared.domain_models import HistoryEvent, HistoryEventType

# Maps "fetch_from" (from ValidateOrder's MissingItem) to the Unit 1 adapter's lookup() function.
_ADAPTER_DISPATCH = {
    "eSIM Provisioning DB": esim_provisioning.lookup,
    "Product Catalog DB": product_catalog.lookup,
    "SIM Inventory DB": sim_inventory.lookup,
    "Number Portability DB": number_portability.lookup,
    "IMEI Registry": imei_registry.lookup,
    "Device Inventory/Stock System": device_inventory.lookup,
    "Billing Profile DB": billing_profile.lookup,
}

# Real gap found during a live team-facing demo (not caught by any prior unit
# test or synth check): _ADAPTER_DISPATCH above never had entries for the 3
# VAS partner adapters (Netflix/Spotify/Disney+), even though ValidateOrder
# (validate_order.py) always generates fetch_from="{vas_type} Partner API"
# for any missing vas_account_ref field. Every VAS fetch hit UNKNOWN_ADAPTER
# and escalated — which LOOKS like correct agent behavior (it did escalate
# safely with a clear reason, per BR-9's safety intent), but is actually
# masking a real, fixable data-fetch gap: the agent should have been able to
# auto-resolve these via the partner's own provision() retry logic, per FR
# test scenario 6 ("VAS entitlement provisioning failure — auto-resolved via
# partner API retry"). Partner adapters use a different interface shape
# (provision(request: dict) -> ProvisionResponse, not lookup(key: str) ->
# LookupResponse) since they implement PartnerAdapter, not DataSourceAdapter
# — a thin shim normalizes this so FetchMissingData can dispatch to either
# shape uniformly.
_VAS_PARTNER_MODULES = {
    "Netflix Partner API": netflix,
    "Spotify Partner API": spotify,
    "Disney+ Partner API": disneyplus,
}


def _vas_partner_adapter_fn(partner_module):
    """Shim: adapts a PartnerAdapter module's provision(request)->ProvisionResponse
    interface to the same lookup(key)->dict-like shape FetchMissingData already
    expects, so both adapter families can be dispatched uniformly. `key` here
    is repurposed as the subscription_id (the partner API's provision() only
    needs subscription_id + retry_attempt, not an arbitrary lookup key)."""

    def _adapter(key: str, retry_attempt: int = 0) -> dict[str, Any]:
        response = partner_module.provision({"subscription_id": key, "retry_attempt": retry_attempt})
        return {
            "success": response.get("success", False),
            "value": response.get("reference_id"),
            "error_type": response.get("error_type"),
            "message": response.get("message", ""),
        }

    return _adapter


def fetch_missing_data(
    order_id: str, subscription_id: str, field: str, fetch_from: str, lookup_key: str, retry_attempt: int = 0
) -> FetchResult:
    """One call per missing field (BR-15). `lookup_key` is whatever identifier
    the target adapter needs (ICCID for eSIM, device_model for stock, etc.) —
    determined by the caller (agent) based on the subscription's other fields.

    `order_id` is required so the resulting history event correlates correctly
    to its parent order (OrderProcessingHistory's partition key)."""
    adapter_fn = _ADAPTER_DISPATCH.get(fetch_from)
    if adapter_fn is not None:
        lookup_response = adapter_fn(lookup_key)
        result = FetchResult(
            subscription_id=subscription_id, field=field, value=lookup_response.get("value"),
            source=fetch_from, success=lookup_response.get("success", False),
            error_type=lookup_response.get("error_type"), message=lookup_response.get("message", ""),
        )
    elif fetch_from in _VAS_PARTNER_MODULES:
        # VAS partner fetch: use subscription_id (not lookup_key) as the
        # provision() call's identifier, and pass retry_attempt through so
        # Netflix's simulated first-attempt-fails-then-succeeds behavior
        # (FR test scenario 6) actually triggers on the real retry.
        vas_adapter_fn = _vas_partner_adapter_fn(_VAS_PARTNER_MODULES[fetch_from])
        lookup_response = vas_adapter_fn(subscription_id, retry_attempt=retry_attempt)
        result = FetchResult(
            subscription_id=subscription_id, field=field, value=lookup_response.get("value"),
            source=fetch_from, success=lookup_response.get("success", False),
            error_type=lookup_response.get("error_type"), message=lookup_response.get("message", ""),
        )
    else:
        result = FetchResult(
            subscription_id=subscription_id, field=field, value=None, source=fetch_from,
            success=False, error_type="UNKNOWN_ADAPTER", message=f"No adapter registered for '{fetch_from}'",
        )

    event_type = HistoryEventType.FETCHED_DATA if result.success else HistoryEventType.BACKEND_ERROR
    history_repository.record_history_event(
        HistoryEvent(
            order_id=order_id,
            subscription_id=subscription_id,
            event_type=event_type,
            tool_name="FetchMissingData",
            summary=f"Fetched {field} from {fetch_from}: {'success' if result.success else 'FAILED'}"
                    + (f" (retry {retry_attempt})" if retry_attempt else ""),
            resulting_status="FETCHED" if result.success else "BACKEND_ERROR",
            details={"field": field, "success": result.success, "retry_attempt": retry_attempt},
        )
    )

    return result


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. Expects event = {"order_id", "subscription_id", "field",
    "fetch_from", "lookup_key", "retry_attempt"}."""
    result = fetch_missing_data(
        order_id=event["order_id"],
        subscription_id=event["subscription_id"],
        field=event["field"],
        fetch_from=event["fetch_from"],
        lookup_key=event.get("lookup_key", ""),
        retry_attempt=event.get("retry_attempt", 0),
    )
    return {
        "subscription_id": result.subscription_id,
        "field": result.field,
        "value": result.value,
        "source": result.source,
        "success": result.success,
        "error_type": result.error_type,
        "message": result.message,
    }
