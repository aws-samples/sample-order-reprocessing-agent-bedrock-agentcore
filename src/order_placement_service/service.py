"""
Order Placement Service — place_order() implementation.

Per business-logic-model.md's place_order() flow, business-rules.md BR-24
through BR-30.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import boto3

from mock_backends.failure_injection_engine.engine import determine_outcome
from mock_backends.repository import (
    order_status_service,
    orders_repository,
    subscriptions_repository,
)
from mock_backends.shared.domain_models import (
    DeviceCategory,
    FinancingType,
    Order,
    OrderCategory,
    OrderStatus,
    Subscription,
    SubscriptionCategory,
    SubscriptionStatus,
)
from order_placement_service.types import DemoModeOverride, DeviceSelection, PlaceOrderRequest, PlaceOrderResult

_EVENTBRIDGE_SOURCE = "crm.orders"
_EVENTBRIDGE_DETAIL_TYPE = "OrderStatusChanged"


def _get_operating_mode() -> str:
    """BR-27/Q1: A — read from environment variable, deployment-time configured."""
    return os.environ.get("OPERATING_MODE", "REALISTIC")


def _find_prior_device_subscription(customer_id: str) -> Optional[tuple[str, str]]:
    """BR-26/Q6: B — automatically look up the customer's most recent ACTIVATED
    Device Purchase/Financing subscription for Upgrade orders, without requiring
    the UI to pass a specific prior_subscription_id.

    Returns (prior_order_id, prior_subscription_id) since CRMOrderSubscriptions'
    partition key is order_id — the caller needs BOTH to correctly address the
    record for the supersede update (a common bug: using the NEW order's id
    instead of the prior subscription's own order_id).

    NOTE: This does a broad scan since there's no customer_id index on
    CRMOrderSubscriptions (v1 scope, per Unit 1's domain-entities.md — no GSI
    needed for current access patterns). Acceptable at samples/workshop scale."""
    all_orders = orders_repository.scan_all_orders()
    candidates = []
    for order in all_orders:
        if order.customer_id != customer_id:
            continue
        subs = subscriptions_repository.query_subscriptions_for_order(order.order_id)
        for sub in subs:
            if sub.subscription_type == "Device Purchase/Financing" and sub.status == SubscriptionStatus.ACTIVATED:
                candidates.append((order.order_id, sub.subscription_id))

    if not candidates:
        return None
    # Most recent by order creation isn't tracked per-subscription; fall back
    # to the first match found (acceptable simplification for v1/demo scope).
    return candidates[0]


def _build_subscriptions(order_id: str, request: PlaceOrderRequest) -> list[Subscription]:
    subscriptions: list[Subscription] = []

    if request.order_category != "Add Subscription":
        mobile_line = Subscription(
            order_id=order_id, subscription_id=f"SUB-{uuid.uuid4().hex[:6].upper()}",
            subscription_category=SubscriptionCategory.CORE_TELCO,
            subscription_type="Mobile Line", provider="eSIM Provisioning",
            plan_id=request.plan_id, sim_type="eSIM",
        )
        subscriptions.append(mobile_line)

        if request.device_selection is not None:
            device_sub = Subscription(
                order_id=order_id, subscription_id=f"SUB-{uuid.uuid4().hex[:6].upper()}",
                subscription_category=SubscriptionCategory.CORE_TELCO,
                subscription_type="Device Purchase/Financing", provider="Device Inventory",
                device_model=request.device_selection.device_model,
                device_category=DeviceCategory(request.device_selection.device_category),
                financing_type=FinancingType(request.device_selection.financing_type),
                esim_compatible=request.device_selection.esim_compatible,
            )
            subscriptions.append(device_sub)

    for vas_type in request.vas_selections:
        vas_sub = Subscription(
            order_id=order_id, subscription_id=f"SUB-{uuid.uuid4().hex[:6].upper()}",
            subscription_category=SubscriptionCategory.VALUE_ADDED_SERVICE,
            subscription_type=vas_type, provider=f"{vas_type} Partner API",
        )
        subscriptions.append(vas_sub)

    return subscriptions


def _fire_order_status_changed_event(order_id: str, failed_subscriptions: list[dict]) -> bool:
    """BR-29: exactly one event per order, listing all failed subscription_ids."""
    try:
        client = boto3.client("events")
        client.put_events(
            Entries=[
                {
                    "Source": _EVENTBRIDGE_SOURCE,
                    "DetailType": _EVENTBRIDGE_DETAIL_TYPE,
                    "Detail": json.dumps(
                        {"order_id": order_id, "status": "FAILED", "failed_subscriptions": failed_subscriptions}
                    ),
                }
            ]
        )
        return True
    except Exception:
        return False


def place_order(request: PlaceOrderRequest) -> PlaceOrderResult:
    """BR-24: always creates a new CRMOrders parent record."""
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    order = Order(
        order_id=order_id, customer_id=request.customer_id,
        order_category=OrderCategory(request.order_category),
        status=OrderStatus.PENDING, created_at=now, updated_at=now,
    )
    orders_repository.create_order(order)

    # BR-26: Upgrade supersede lookup (automatic, per Q6: B)
    if request.order_category == "Upgrade":
        prior = _find_prior_device_subscription(request.customer_id)
        if prior is not None:
            prior_order_id, prior_subscription_id = prior
            subscriptions_repository.mark_superseded(prior_order_id, prior_subscription_id)

    subscriptions = _build_subscriptions(order_id, request)
    for sub in subscriptions:
        subscriptions_repository.create_subscription(sub)
    order.subscriptions = subscriptions

    # BR-27/BR-28: mode determination with graceful fallback
    mode = _get_operating_mode()
    if mode == "DEMO" and request.demo_mode_override is not None:
        outcome = determine_outcome(
            order, mode="DEMO",
            forced_scenario=request.demo_mode_override.forced_scenario,
            forced_subscription_id=_pick_subscription_for_override(
                subscriptions, request.demo_mode_override.forced_subscription_type
            ),
        )
    else:
        outcome = determine_outcome(order, mode="REALISTIC")

    if outcome.will_fail:
        _apply_failure_to_subscription(order_id, outcome.failure_subscription_id, outcome.scenario)
        event_fired = _fire_order_status_changed_event(
            order_id,
            [{"subscription_id": outcome.failure_subscription_id, "scenario": outcome.scenario,
              "is_non_fetchable": outcome.is_non_fetchable}],
        )
        order_status_service.recompute_and_persist_order_status(order_id, now)
        return PlaceOrderResult(
            order_id=order_id, subscription_ids=[s.subscription_id for s in subscriptions],
            initial_outcome="WILL_FAIL", event_fired=event_fired,
            failure_subscription_id=outcome.failure_subscription_id, scenario=outcome.scenario,
        )

    # No failure: activate everything directly, no agent invocation needed (BR-29)
    for sub in subscriptions:
        subscriptions_repository.transition_status_idempotent(
            order_id, sub.subscription_id, SubscriptionStatus.ACTIVATED,
            allowed_current_statuses=[SubscriptionStatus.PENDING],
        )
    order_status_service.recompute_and_persist_order_status(order_id, now)

    return PlaceOrderResult(
        order_id=order_id, subscription_ids=[s.subscription_id for s in subscriptions],
        initial_outcome="WILL_SUCCEED", event_fired=False,
    )


def _pick_subscription_for_override(subscriptions: list[Subscription], forced_subscription_type: str) -> str:
    for sub in subscriptions:
        if sub.subscription_type == forced_subscription_type:
            return sub.subscription_id
    return subscriptions[0].subscription_id if subscriptions else ""


def _apply_failure_to_subscription(order_id: str, subscription_id: str, scenario: Optional[str]) -> None:
    """Nulls the relevant field(s) and sets FAILED status for the target subscription,
    per business_logic_model.md's Failure Injection Algorithm step 2b (Unit 1)."""
    subscriptions_repository.transition_status_idempotent(
        order_id, subscription_id, SubscriptionStatus.FAILED,
        allowed_current_statuses=[SubscriptionStatus.PENDING],
    )
    subscriptions_repository.update_subscription_fields(order_id, subscription_id, {"failure_reason": scenario})


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. Expects event matching PlaceOrderRequest's fields."""
    device_selection = None
    if event.get("device_selection"):
        device_selection = DeviceSelection(**event["device_selection"])

    demo_override = None
    if event.get("demo_mode_override"):
        demo_override = DemoModeOverride(**event["demo_mode_override"])

    request = PlaceOrderRequest(
        customer_id=event["customer_id"],
        order_category=event["order_category"],
        plan_id=event.get("plan_id", ""),
        device_selection=device_selection,
        vas_selections=event.get("vas_selections", []),
        demo_mode_override=demo_override,
    )
    result = place_order(request)
    return {
        "order_id": result.order_id,
        "subscription_ids": result.subscription_ids,
        "initial_outcome": result.initial_outcome,
        "event_fired": result.event_fired,
        "failure_subscription_id": result.failure_subscription_id,
        "scenario": result.scenario,
    }
