"""
ValidateOrder tool — determines which required fields are missing across all
subscription items in an order. Operates on in-memory data already fetched by
GetOrderDetails (BR-14) — does NOT independently re-query the database.

Per components.md (1.2), business-rules.md BR-4 (Unit 1) / BR-14 (Unit 2),
business-logic-model.md step [2].
"""

from __future__ import annotations

from typing import Any

from agent.shared.tool_types import MissingItem, ValidationResult
from mock_backends.repository import history_repository
from mock_backends.shared.domain_models import HistoryEvent, HistoryEventType, Order, SubscriptionCategory

# BR-4 (Unit 1): required fields per subscription_type.
_REQUIRED_FIELDS: dict[str, dict[str, str]] = {
    "Mobile Line": {
        "msisdn": "Number Portability DB",
        "sim_type": "eSIM Provisioning DB",
        "activation_code": "eSIM Provisioning DB",
        "iccid": "SIM Inventory DB",
        "plan_id": "Product Catalog DB",
    },
    "Device Purchase/Financing": {
        "device_model": "Device Inventory/Stock System",
        "financing_type": "Device Inventory/Stock System",
        "imei": "IMEI Registry",
        "stock_status": "Device Inventory/Stock System",
    },
}

_VAS_REQUIRED_FIELDS = {
    "vas_account_ref": "{vas_type} Partner API",
}


def validate_order(order: Order) -> ValidationResult:
    """BR-14: operates on the in-memory Order object (with subscriptions already
    populated by GetOrderDetails), not a fresh database query."""
    missing_items: list[MissingItem] = []

    for sub in order.subscriptions:
        if sub.subscription_category == SubscriptionCategory.VALUE_ADDED_SERVICE:
            required = {k: v.format(vas_type=sub.subscription_type) for k, v in _VAS_REQUIRED_FIELDS.items()}
        else:
            required = _REQUIRED_FIELDS.get(sub.subscription_type, {})

        for field_name, fetch_from in required.items():
            if getattr(sub, field_name, None) is None:
                missing_items.append(
                    MissingItem(subscription_id=sub.subscription_id, missing_field=field_name, fetch_from=fetch_from)
                )

    result = ValidationResult(order_id=order.order_id, missing_items=missing_items)

    history_repository.record_history_event(
        HistoryEvent(
            order_id=order.order_id,
            event_type=HistoryEventType.VALIDATED,
            tool_name="ValidateOrder",
            summary=f"Validation found {len(missing_items)} missing field(s)" if missing_items
                    else "All required fields present",
            resulting_status=order.status.value,
            details={"missing_items": [vars(m) for m in missing_items]},
        )
    )

    return result


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. Expects event = GetOrderDetails' output dict (in-memory
    per BR-14 — this tool is invoked by the agent with the prior tool's output,
    not by re-fetching from the database)."""
    from mock_backends.shared.domain_models import Subscription

    order = Order.from_item(event)
    order.subscriptions = [Subscription.from_item(s) for s in event.get("subscriptions", [])]

    result = validate_order(order)
    return {
        "order_id": result.order_id,
        "missing_items": [vars(m) for m in result.missing_items],
        "all_valid": result.all_valid,
    }
