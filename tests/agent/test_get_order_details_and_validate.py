"""Unit tests for GetOrderDetails and ValidateOrder tools."""

from __future__ import annotations

import pytest

from agent.tools.get_order_details import get_order_details
from agent.tools.validate_order import validate_order
from mock_backends.repository import orders_repository, subscriptions_repository
from mock_backends.shared.domain_models import (
    Order,
    OrderCategory,
    Subscription,
    SubscriptionCategory,
)


def test_get_order_details_fetches_order_and_subscriptions(dynamodb_tables):
    order = Order(order_id="ORD-1", customer_id="CUST-1", order_category=OrderCategory.NEW_CONNECTION)
    orders_repository.create_order(order)
    sub = Subscription(
        order_id="ORD-1", subscription_id="SUB-1",
        subscription_category=SubscriptionCategory.CORE_TELCO,
        subscription_type="Mobile Line", provider="eSIM Provisioning",
    )
    subscriptions_repository.create_subscription(sub)

    result = get_order_details("ORD-1")
    assert result.order_id == "ORD-1"
    assert len(result.subscriptions) == 1
    assert result.subscriptions[0].subscription_id == "SUB-1"


def test_get_order_details_raises_for_missing_order(dynamodb_tables):
    with pytest.raises(ValueError):
        get_order_details("ORD-DOES-NOT-EXIST")


def test_validate_order_detects_missing_activation_code(dynamodb_tables):
    order = Order(order_id="ORD-2", customer_id="CUST-1", order_category=OrderCategory.NEW_CONNECTION)
    order.subscriptions = [
        Subscription(
            order_id="ORD-2", subscription_id="SUB-1",
            subscription_category=SubscriptionCategory.CORE_TELCO,
            subscription_type="Mobile Line", provider="eSIM Provisioning",
            msisdn="919812345678", sim_type="eSIM", iccid="8991000000000000001", plan_id="POST5G999",
            activation_code=None,  # missing
        )
    ]

    result = validate_order(order)
    assert not result.all_valid
    assert len(result.missing_items) == 1
    assert result.missing_items[0].missing_field == "activation_code"
    assert result.missing_items[0].fetch_from == "eSIM Provisioning DB"


def test_validate_order_all_valid_when_no_missing_fields(dynamodb_tables):
    order = Order(order_id="ORD-3", customer_id="CUST-1", order_category=OrderCategory.NEW_CONNECTION)
    order.subscriptions = [
        Subscription(
            order_id="ORD-3", subscription_id="SUB-1",
            subscription_category=SubscriptionCategory.CORE_TELCO,
            subscription_type="Mobile Line", provider="eSIM Provisioning",
            msisdn="919812345678", sim_type="eSIM", iccid="8991000000000000001",
            plan_id="POST5G999", activation_code="LPA:1$abc",
        )
    ]

    result = validate_order(order)
    assert result.all_valid
    assert len(result.missing_items) == 0


def test_validate_order_detects_multiple_missing_fields(dynamodb_tables):
    """Scenario 4: multiple missing Core Telco fields in one order."""
    order = Order(order_id="ORD-4", customer_id="CUST-1", order_category=OrderCategory.NEW_CONNECTION)
    order.subscriptions = [
        Subscription(
            order_id="ORD-4", subscription_id="SUB-1",
            subscription_category=SubscriptionCategory.CORE_TELCO,
            subscription_type="Mobile Line", provider="eSIM Provisioning",
            msisdn=None, sim_type="eSIM", iccid=None, plan_id="POST5G999", activation_code=None,
        )
    ]
    result = validate_order(order)
    assert len(result.missing_items) == 3  # msisdn, iccid, activation_code


def test_validate_order_detects_missing_vas_field(dynamodb_tables):
    order = Order(order_id="ORD-5", customer_id="CUST-1", order_category=OrderCategory.ADD_SUBSCRIPTION)
    order.subscriptions = [
        Subscription(
            order_id="ORD-5", subscription_id="SUB-1",
            subscription_category=SubscriptionCategory.VALUE_ADDED_SERVICE,
            subscription_type="Netflix", provider="Netflix Partner API",
            vas_account_ref=None,
        )
    ]
    result = validate_order(order)
    assert len(result.missing_items) == 1
    assert result.missing_items[0].fetch_from == "Netflix Partner API"
