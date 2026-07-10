#!/usr/bin/env python3
"""
seed_crm.py — Seeds the mock CRM (CRMOrders + CRMOrderSubscriptions) with 100
realistic multi-subscription orders, per FR-15 and BR-13.

BR-13: includes a representative mix of all 5 order statuses (not all PENDING)
so that Order Summary, Issues, and Order History tabs have meaningful content
immediately — supporting the workshop's "Module 2: Explore the Data Layer"
exercise (see unit-of-work-dependency.md's Deployment Checkpoint Sequencing).

Run this manually once, after the CDK deployment completes (see
deployment-architecture.md's Post-Deployment Steps):

    python -m mock_backends.seed.seed_crm
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from mock_backends.repository import orders_repository, subscriptions_repository
from mock_backends.shared.domain_models import (
    DeviceCategory,
    FinancingType,
    Order,
    OrderCategory,
    OrderStatus,
    StockStatus,
    Subscription,
    SubscriptionCategory,
    SubscriptionStatus,
)

TOTAL_ORDERS = 100

_DEVICE_MODELS = [
    ("iPhone 16 Pro Max", DeviceCategory.FLAGSHIP),
    ("Samsung Galaxy Z Fold 6", DeviceCategory.FOLDABLE),
    ("Samsung Galaxy S24", DeviceCategory.STANDARD),
]

_PLANS = ["POST5G999", "POST5G050", "PRE0BASIC"]

_VAS_TYPES = ["Netflix", "Spotify", "Disney+"]

# BR-13: representative status distribution — not all PENDING.
_STATUS_WEIGHTS = {
    OrderStatus.ACTIVATED: 0.55,
    OrderStatus.PENDING: 0.10,
    OrderStatus.FAILED: 0.10,
    OrderStatus.PARTIALLY_ACTIVATED: 0.15,
    OrderStatus.ESCALATED: 0.10,
}


def _weighted_status_choice() -> OrderStatus:
    statuses, weights = zip(*_STATUS_WEIGHTS.items())
    return random.choices(statuses, weights=weights, k=1)[0]  # nosec B311 -- fake seed data, not crypto


def _subscription_status_for_order_status(order_status: OrderStatus, index: int, total: int) -> SubscriptionStatus:
    """Pick a plausible subscription status consistent with the parent order's
    (target) derived status, per BR-3."""
    if order_status == OrderStatus.ACTIVATED:
        return SubscriptionStatus.ACTIVATED
    if order_status == OrderStatus.PENDING:
        return SubscriptionStatus.PENDING
    if order_status == OrderStatus.FAILED:
        return SubscriptionStatus.FAILED
    if order_status == OrderStatus.PARTIALLY_ACTIVATED:
        return SubscriptionStatus.ACTIVATED if index % 2 == 0 else SubscriptionStatus.FAILED
    if order_status == OrderStatus.ESCALATED:
        return SubscriptionStatus.FAILED if index == 0 else SubscriptionStatus.ACTIVATED
    return SubscriptionStatus.PENDING


def _build_order(index: int) -> tuple[Order, list[Subscription]]:
    order_id = f"ORD-{10000 + index}"
    customer_id = f"CUST-{80000 + index}"
    order_category = random.choice(list(OrderCategory))  # nosec B311 -- fake seed data, not crypto
    target_status = _weighted_status_choice()

    order = Order(
        order_id=order_id,
        customer_id=customer_id,
        order_category=order_category,
        status=target_status,
        created_at=(datetime.now(timezone.utc) - timedelta(days=random.randint(0, 30))).isoformat(),  # nosec B311 -- fake seed data, not crypto
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    subscriptions: list[Subscription] = []

    # Core mobile line (always present)
    device_model, device_category = random.choice(_DEVICE_MODELS)  # nosec B311 -- fake seed data, not crypto
    mobile_line = Subscription(
        order_id=order_id,
        subscription_id=f"SUB-{uuid.uuid4().hex[:6].upper()}",
        subscription_category=SubscriptionCategory.CORE_TELCO,
        subscription_type="Mobile Line",
        provider="eSIM Provisioning",
        status=_subscription_status_for_order_status(target_status, 0, 2),
        msisdn=f"9198{random.randint(10000000, 99999999)}",  # nosec B311 -- fake seed data, not crypto
        sim_type="eSIM",
        activation_code=f"LPA:1$rsp.provider.com${uuid.uuid4().hex[:6].upper()}",
        iccid="8991" + "".join(str(random.randint(0, 9)) for _ in range(15)),  # nosec B311 -- fake seed data, not crypto
        plan_id=random.choice(_PLANS),  # nosec B311 -- fake seed data, not crypto
    )
    subscriptions.append(mobile_line)

    # Device subscription, for New Connection and Upgrade categories
    if order_category in (OrderCategory.NEW_CONNECTION, OrderCategory.UPGRADE):
        device_sub = Subscription(
            order_id=order_id,
            subscription_id=f"SUB-{uuid.uuid4().hex[:6].upper()}",
            subscription_category=SubscriptionCategory.CORE_TELCO,
            subscription_type="Device Purchase/Financing",
            provider="Device Inventory",
            status=_subscription_status_for_order_status(target_status, 1, 2),
            device_model=device_model,
            device_category=device_category,
            financing_type=random.choice(list(FinancingType)),  # nosec B311 -- fake seed data, not crypto
            imei="".join(str(random.randint(0, 9)) for _ in range(15)),  # nosec B311 -- fake seed data, not crypto
            stock_status=StockStatus.IN_STOCK if device_category != DeviceCategory.FOLDABLE else StockStatus.BACKORDER,
            esim_compatible=True,
        )
        subscriptions.append(device_sub)

    # Occasionally add a VAS subscription
    if random.random() < 0.4:  # nosec B311 -- fake seed data, not crypto
        vas_type = random.choice(_VAS_TYPES)  # nosec B311 -- fake seed data, not crypto
        vas_sub = Subscription(
            order_id=order_id,
            subscription_id=f"SUB-{uuid.uuid4().hex[:6].upper()}",
            subscription_category=SubscriptionCategory.VALUE_ADDED_SERVICE,
            subscription_type=vas_type,
            provider=f"{vas_type} Partner API",
            status=_subscription_status_for_order_status(target_status, len(subscriptions), len(subscriptions) + 1),
            depends_on=mobile_line.subscription_id,
            vas_account_ref=f"VAS-{uuid.uuid4().hex[:8]}",
            vas_entitlement_status="ACTIVE" if target_status == OrderStatus.ACTIVATED else "PENDING",
        )
        subscriptions.append(vas_sub)

    return order, subscriptions


def seed() -> None:
    print(f"Seeding {TOTAL_ORDERS} orders into CRMOrders / CRMOrderSubscriptions...")
    for i in range(TOTAL_ORDERS):
        order, subscriptions = _build_order(i)
        orders_repository.create_order(order)
        for sub in subscriptions:
            subscriptions_repository.create_subscription(sub)
    print(f"Done. {TOTAL_ORDERS} orders written.")


if __name__ == "__main__":
    seed()
