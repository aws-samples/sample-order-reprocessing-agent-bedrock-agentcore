"""Unit tests for order_summary and issues tab logic functions."""

from __future__ import annotations

from mock_backends.repository import orders_repository, subscriptions_repository
from mock_backends.shared.domain_models import (
    Order,
    OrderCategory,
    OrderStatus,
    Subscription,
    SubscriptionCategory,
    SubscriptionStatus,
)
from ui.tabs.issues import get_issues
from ui.tabs.order_summary import get_all_orders_summary, get_order_detail


def test_get_all_orders_summary_returns_all_orders(dynamodb_tables):
    orders_repository.create_order(
        Order(order_id="ORD-1", customer_id="CUST-1", order_category=OrderCategory.NEW_CONNECTION)
    )
    orders_repository.create_order(
        Order(order_id="ORD-2", customer_id="CUST-2", order_category=OrderCategory.UPGRADE)
    )

    summary = get_all_orders_summary()
    assert len(summary) == 2
    order_ids = {o["order_id"] for o in summary}
    assert order_ids == {"ORD-1", "ORD-2"}


def test_get_order_detail_returns_subscriptions(dynamodb_tables):
    orders_repository.create_order(
        Order(order_id="ORD-3", customer_id="CUST-1", order_category=OrderCategory.NEW_CONNECTION)
    )
    subscriptions_repository.create_subscription(
        Subscription(
            order_id="ORD-3", subscription_id="SUB-1",
            subscription_category=SubscriptionCategory.CORE_TELCO,
            subscription_type="Mobile Line", provider="eSIM Provisioning",
        )
    )

    detail = get_order_detail("ORD-3")
    assert len(detail) == 1
    assert detail[0]["subscription_id"] == "SUB-1"


def test_get_issues_returns_escalated_orders(dynamodb_tables):
    orders_repository.create_order(
        Order(order_id="ORD-4", customer_id="CUST-1", order_category=OrderCategory.ADD_SUBSCRIPTION,
              status=OrderStatus.ESCALATED)
    )
    subscriptions_repository.create_subscription(
        Subscription(
            order_id="ORD-4", subscription_id="SUB-2",
            subscription_category=SubscriptionCategory.VALUE_ADDED_SERVICE,
            subscription_type="Disney+", provider="Disney+ Partner API",
            status=SubscriptionStatus.FAILED, failure_reason="region_lock",
        )
    )

    issues = get_issues()
    assert len(issues) == 1
    assert issues[0]["order_id"] == "ORD-4"
    assert issues[0]["failed_subscriptions"][0]["failure_reason"] == "region_lock"


def test_get_issues_excludes_healthy_orders(dynamodb_tables):
    orders_repository.create_order(
        Order(order_id="ORD-5", customer_id="CUST-1", order_category=OrderCategory.NEW_CONNECTION,
              status=OrderStatus.ACTIVATED)
    )

    issues = get_issues()
    assert len(issues) == 0
