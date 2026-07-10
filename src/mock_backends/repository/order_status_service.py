"""
Order/Subscription status derivation logic (BR-3) and Upgrade supersede
orchestration (BR-2), per business-logic-model.md.

Order status is always DERIVED from child subscription statuses, never set
directly.
"""

from __future__ import annotations

from mock_backends.repository import orders_repository, subscriptions_repository
from mock_backends.shared.domain_models import (
    Order,
    OrderCategory,
    OrderStatus,
    Subscription,
    SubscriptionStatus,
)


def derive_order_status(subscriptions: list[Subscription]) -> OrderStatus:
    """BR-3: derive parent order status from child subscription statuses.
    SUPERSEDED items are excluded from this derivation."""
    active_subs = [s for s in subscriptions if s.status != SubscriptionStatus.SUPERSEDED]

    if not active_subs:
        return OrderStatus.PENDING

    statuses = {s.status for s in active_subs}

    if statuses == {SubscriptionStatus.ACTIVATED}:
        return OrderStatus.ACTIVATED

    if SubscriptionStatus.ACTIVATED in statuses and len(statuses) > 1:
        return OrderStatus.PARTIALLY_ACTIVATED

    if statuses <= {SubscriptionStatus.FAILED, SubscriptionStatus.PENDING} and SubscriptionStatus.FAILED in statuses:
        return OrderStatus.FAILED

    return OrderStatus.PENDING


def recompute_and_persist_order_status(order_id: str, updated_at: str) -> OrderStatus:
    """Called by Unit 2's tools after any subscription status change, per
    services.md's Order Reprocessing Service orchestration."""
    subscriptions = subscriptions_repository.query_subscriptions_for_order(order_id)
    new_status = derive_order_status(subscriptions)
    orders_repository.update_order_status(order_id, new_status, updated_at)
    return new_status


def apply_escalation(subscriptions: list[Subscription]) -> OrderStatus:
    """BR-3 special case: any subscription hitting an unresolvable/escalated
    condition drives the order to ESCALATED, taking precedence over the
    normal ACTIVATED/FAILED/PARTIALLY_ACTIVATED derivation. This function is
    called explicitly by EscalateToHuman (Unit 2) rather than being inferred
    purely from subscription status values, since ESCALATED is an order-level
    concept without a matching SubscriptionStatus enum value."""
    return OrderStatus.ESCALATED


def apply_upgrade_supersede(
    order: Order,
    prior_subscription_id: str,
    new_subscription: Subscription,
) -> None:
    """BR-2/BR-28: for order_category=Upgrade, mark the customer's prior device
    subscription as SUPERSEDED and create a new subscription item for the
    replacement device, within the new order (per business-logic-model.md's
    Upgrade Order Supersede Logic)."""
    if order.order_category != OrderCategory.UPGRADE:
        raise ValueError("apply_upgrade_supersede should only be called for Upgrade orders")

    subscriptions_repository.mark_superseded(order.order_id, prior_subscription_id)
    subscriptions_repository.create_subscription(new_subscription)
