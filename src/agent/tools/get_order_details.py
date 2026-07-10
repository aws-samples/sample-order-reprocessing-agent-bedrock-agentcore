"""
GetOrderDetails tool — fetches the full order record and all associated
subscription items from Unit 1's mock CRM.

Per components.md (1.1), component-methods.md, business-logic-model.md step [1].
"""

from __future__ import annotations

from typing import Any

from mock_backends.repository import history_repository, orders_repository, subscriptions_repository
from mock_backends.shared.domain_models import HistoryEvent, HistoryEventType, Order


def get_order_details(order_id: str) -> Order:
    """Fetches the parent order and attaches all its subscription items."""
    order = orders_repository.get_order(order_id)
    if order is None:
        raise ValueError(f"Order {order_id} not found")

    order.subscriptions = subscriptions_repository.query_subscriptions_for_order(order_id)

    history_repository.record_history_event(
        HistoryEvent(
            order_id=order_id,
            event_type=HistoryEventType.DETECTED,
            tool_name="GetOrderDetails",
            summary=f"Order {order_id} status {order.status.value} — fetched full order details "
                    f"with {len(order.subscriptions)} subscription item(s)",
            resulting_status=order.status.value,
            details={"subscription_count": len(order.subscriptions)},
        )
    )

    return order


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. Expects event = {"order_id": "..."}."""
    order = get_order_details(event["order_id"])
    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "order_category": order.order_category.value,
        "status": order.status.value,
        "subscriptions": [s.to_item() for s in order.subscriptions],
    }
