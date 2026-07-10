"""
Ambient Activity Generator — simulates other customers placing orders,
per BR-31/32/33. Triggered by an EventBridge Scheduler (default 1-minute
interval) AND manually invokable (e.g., from Unit 4's UI or AWS CLI).
"""

from __future__ import annotations

import random
import uuid
from typing import Any

from order_placement_service.service import place_order
from order_placement_service.types import DeviceSelection, PlaceOrderRequest

_ORDER_CATEGORIES = ["New Connection", "Upgrade", "Add Subscription"]
_DEVICE_MODELS = [
    ("iPhone 16 Pro Max", "Flagship"),
    ("Samsung Galaxy Z Fold 6", "Foldable"),
    ("Samsung Galaxy S24", "Standard"),
]
_FINANCING_TYPES = ["Full Payment", "Installment-12mo", "Installment-24mo", "Trade-in + Installment"]
_PLANS = ["POST5G999", "POST5G050", "PRE0BASIC"]
_VAS_TYPES = ["Netflix", "Spotify", "Disney+"]


def _generate_random_request() -> PlaceOrderRequest:
    """BR-33: generates a plausible, randomized PlaceOrderRequest simulating
    an independent customer's order — uses the same place_order() code path
    as a real UI-triggered order, no special-casing."""
    customer_id = f"CUST-AMBIENT-{uuid.uuid4().hex[:6].upper()}"
    order_category = random.choice(_ORDER_CATEGORIES)

    device_selection = None
    if order_category != "Add Subscription":
        device_model, device_category = random.choice(_DEVICE_MODELS)
        device_selection = DeviceSelection(
            device_model=device_model, device_category=device_category,
            financing_type=random.choice(_FINANCING_TYPES),
        )

    vas_selections = random.sample(_VAS_TYPES, k=random.randint(0, 2))

    return PlaceOrderRequest(
        customer_id=customer_id, order_category=order_category,
        plan_id=random.choice(_PLANS), device_selection=device_selection,
        vas_selections=vas_selections,
    )


def generate_ambient_activity() -> dict[str, Any]:
    """Entry point called by both the EventBridge Scheduler and manual invocation."""
    request = _generate_random_request()
    result = place_order(request)
    return {
        "order_id": result.order_id,
        "customer_id": request.customer_id,
        "order_category": request.order_category,
        "initial_outcome": result.initial_outcome,
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. No required input — works identically whether invoked
    by the EventBridge Scheduler (empty event) or manually (event ignored)."""
    return generate_ambient_activity()
