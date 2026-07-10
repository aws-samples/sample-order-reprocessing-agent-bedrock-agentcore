"""Unit tests for the repository layer (mock_backends/repository/*.py) using
moto-mocked DynamoDB. Covers CRUD operations and BR-12 idempotency behavior."""

from __future__ import annotations

import importlib

import pytest

from mock_backends.shared.domain_models import (
    HistoryEvent,
    HistoryEventType,
    Order,
    OrderCategory,
    OrderStatus,
    Subscription,
    SubscriptionCategory,
    SubscriptionStatus,
)


@pytest.fixture(autouse=True)
def _reload_repository_modules(dynamodb_tables):
    """boto3 resources are created lazily inside each repository function
    (_table()), so no module reload is strictly needed, but we keep this
    fixture to make the dependency on dynamodb_tables explicit and ordered
    before repository imports execute their calls."""
    yield


def test_create_and_get_order():
    from mock_backends.repository import orders_repository

    order = Order(order_id="ORD-100", customer_id="CUST-1", order_category=OrderCategory.NEW_CONNECTION)
    orders_repository.create_order(order)

    fetched = orders_repository.get_order("ORD-100")
    assert fetched is not None
    assert fetched.customer_id == "CUST-1"
    assert fetched.status == OrderStatus.PENDING


def test_get_order_returns_none_when_missing():
    from mock_backends.repository import orders_repository

    assert orders_repository.get_order("ORD-DOES-NOT-EXIST") is None


def test_update_order_status_succeeds_for_existing_order():
    from mock_backends.repository import orders_repository

    order = Order(order_id="ORD-101", customer_id="CUST-1", order_category=OrderCategory.NEW_CONNECTION)
    orders_repository.create_order(order)

    result = orders_repository.update_order_status("ORD-101", OrderStatus.ACTIVATED, "2026-01-01T00:00:00Z")
    assert result is True

    fetched = orders_repository.get_order("ORD-101")
    assert fetched.status == OrderStatus.ACTIVATED


def test_update_order_status_fails_for_nonexistent_order():
    from mock_backends.repository import orders_repository

    result = orders_repository.update_order_status("ORD-NOPE", OrderStatus.ACTIVATED, "2026-01-01T00:00:00Z")
    assert result is False


def test_query_orders_by_status_uses_gsi():
    from mock_backends.repository import orders_repository

    o1 = Order(order_id="ORD-200", customer_id="CUST-2", order_category=OrderCategory.NEW_CONNECTION,
               status=OrderStatus.ESCALATED)
    o2 = Order(order_id="ORD-201", customer_id="CUST-3", order_category=OrderCategory.NEW_CONNECTION,
               status=OrderStatus.ACTIVATED)
    orders_repository.create_order(o1)
    orders_repository.create_order(o2)

    escalated = orders_repository.query_orders_by_status(OrderStatus.ESCALATED)
    assert len(escalated) == 1
    assert escalated[0].order_id == "ORD-200"


def test_scan_all_orders():
    from mock_backends.repository import orders_repository

    orders_repository.create_order(Order(order_id="ORD-300", customer_id="C1", order_category=OrderCategory.NEW_CONNECTION))
    orders_repository.create_order(Order(order_id="ORD-301", customer_id="C2", order_category=OrderCategory.NEW_CONNECTION))

    all_orders = orders_repository.scan_all_orders()
    assert len(all_orders) == 2


def test_create_and_query_subscriptions_for_order():
    from mock_backends.repository import subscriptions_repository

    sub = Subscription(
        order_id="ORD-400", subscription_id="SUB-1",
        subscription_category=SubscriptionCategory.CORE_TELCO,
        subscription_type="Mobile Line", provider="eSIM Provisioning",
    )
    subscriptions_repository.create_subscription(sub)

    fetched = subscriptions_repository.query_subscriptions_for_order("ORD-400")
    assert len(fetched) == 1
    assert fetched[0].subscription_id == "SUB-1"


def test_update_subscription_fields():
    from mock_backends.repository import subscriptions_repository

    sub = Subscription(
        order_id="ORD-401", subscription_id="SUB-2",
        subscription_category=SubscriptionCategory.CORE_TELCO,
        subscription_type="Mobile Line", provider="eSIM Provisioning",
    )
    subscriptions_repository.create_subscription(sub)

    subscriptions_repository.update_subscription_fields(
        "ORD-401", "SUB-2", {"activation_code": "LPA:1$rsp.provider.com$ABC123"}
    )

    fetched = subscriptions_repository.get_subscription("ORD-401", "SUB-2")
    assert fetched.activation_code == "LPA:1$rsp.provider.com$ABC123"


def test_transition_status_idempotent_succeeds_once():
    """BR-12: the first ACTIVATED transition succeeds; a duplicate retry
    (simulating agent/Lambda/EventBridge retry) is a no-op, not a double-apply."""
    from mock_backends.repository import subscriptions_repository

    sub = Subscription(
        order_id="ORD-402", subscription_id="SUB-3",
        subscription_category=SubscriptionCategory.CORE_TELCO,
        subscription_type="Mobile Line", provider="eSIM Provisioning",
        status=SubscriptionStatus.FAILED,
    )
    subscriptions_repository.create_subscription(sub)

    first_attempt = subscriptions_repository.transition_status_idempotent(
        "ORD-402", "SUB-3", SubscriptionStatus.ACTIVATED,
        allowed_current_statuses=[SubscriptionStatus.FAILED, SubscriptionStatus.PENDING],
    )
    assert first_attempt is True

    # Retry: subscription is now ACTIVATED, so it's no longer in allowed_current_statuses
    retry_attempt = subscriptions_repository.transition_status_idempotent(
        "ORD-402", "SUB-3", SubscriptionStatus.ACTIVATED,
        allowed_current_statuses=[SubscriptionStatus.FAILED, SubscriptionStatus.PENDING],
    )
    assert retry_attempt is False  # idempotent no-op, not an error


def test_mark_superseded_only_from_activated():
    from mock_backends.repository import subscriptions_repository

    sub = Subscription(
        order_id="ORD-403", subscription_id="SUB-4",
        subscription_category=SubscriptionCategory.CORE_TELCO,
        subscription_type="Device Purchase/Financing", provider="Device Inventory",
        status=SubscriptionStatus.ACTIVATED,
    )
    subscriptions_repository.create_subscription(sub)

    result = subscriptions_repository.mark_superseded("ORD-403", "SUB-4")
    assert result is True

    fetched = subscriptions_repository.get_subscription("ORD-403", "SUB-4")
    assert fetched.status == SubscriptionStatus.SUPERSEDED


def test_record_and_query_history_events_chronological():
    from mock_backends.repository import history_repository

    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-500", event_type=HistoryEventType.DETECTED,
            tool_name="AgentCoreRuntime", summary="Order failed", resulting_status="FAILED",
            event_timestamp="2026-01-01T00:00:01Z",
        )
    )
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-500", event_type=HistoryEventType.VALIDATED,
            tool_name="ValidateOrder", summary="Missing activation_code", resulting_status="FAILED",
            event_timestamp="2026-01-01T00:00:02Z",
        )
    )

    events = history_repository.query_history_for_order("ORD-500")
    assert len(events) == 2
    assert events[0].event_type == HistoryEventType.DETECTED
    assert events[1].event_type == HistoryEventType.VALIDATED  # chronological order preserved
