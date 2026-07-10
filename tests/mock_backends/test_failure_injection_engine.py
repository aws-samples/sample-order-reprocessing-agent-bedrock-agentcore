"""Unit tests for the Failure Injection Engine (mock_backends/failure_injection_engine/engine.py).

Covers: Realistic Mode probability weighting, Demo Mode determinism,
business-rule-block (non-fetchable) tagging (BR-9).
"""

from __future__ import annotations

import pytest

from mock_backends.failure_injection_engine.engine import determine_outcome
from mock_backends.shared.domain_models import (
    DeviceCategory,
    FinancingType,
    Order,
    OrderCategory,
    Subscription,
    SubscriptionCategory,
)

TEST_CONFIG = {
    "base_failure_rate": 1.0,  # force certain failure for deterministic tests
    "weights": {
        "device_category": {"Foldable": 1.0, "Flagship": 1.0, "Standard": 1.0},
        "vas_type": {"Disney+": 1.0, "Netflix": 1.0, "Spotify": 1.0},
        "order_category": {"Upgrade": 1.0, "New Connection": 1.0, "Add Subscription": 1.0},
    },
    "scenario_pools": {
        "core_telco": ["missing_activation_code"],
        "device": ["imei_validation_failure", "stock_backorder", "foldable_esim_quirk", "trade_in_valuation_mismatch"],
        "vas": ["entitlement_failure", "region_lock", "billing_profile_missing"],
    },
    "non_fetchable_scenarios": ["region_lock", "trade_in_valuation_mismatch"],
}

ZERO_FAILURE_CONFIG = {**TEST_CONFIG, "base_failure_rate": 0.0}


def _make_core_telco_order() -> Order:
    order = Order(order_id="ORD-1", customer_id="CUST-1", order_category=OrderCategory.NEW_CONNECTION)
    order.subscriptions.append(
        Subscription(
            order_id="ORD-1",
            subscription_id="SUB-1",
            subscription_category=SubscriptionCategory.CORE_TELCO,
            subscription_type="Mobile Line",
            provider="eSIM Provisioning",
        )
    )
    return order


def _make_vas_order() -> Order:
    order = Order(order_id="ORD-2", customer_id="CUST-2", order_category=OrderCategory.ADD_SUBSCRIPTION)
    order.subscriptions.append(
        Subscription(
            order_id="ORD-2",
            subscription_id="SUB-2",
            subscription_category=SubscriptionCategory.VALUE_ADDED_SERVICE,
            subscription_type="Disney+",
            provider="Disney+ Partner API",
        )
    )
    return order


def test_realistic_mode_no_failure_when_rate_is_zero():
    order = _make_core_telco_order()
    decision = determine_outcome(order, mode="REALISTIC", config=ZERO_FAILURE_CONFIG)
    assert decision.will_fail is False
    assert decision.failure_subscription_id is None


def test_realistic_mode_always_fails_when_rate_is_one():
    order = _make_core_telco_order()
    decision = determine_outcome(order, mode="REALISTIC", config=TEST_CONFIG)
    assert decision.will_fail is True
    assert decision.failure_subscription_id == "SUB-1"
    assert decision.scenario == "missing_activation_code"
    assert decision.is_non_fetchable is False


def test_demo_mode_is_deterministic():
    order = _make_core_telco_order()
    decision = determine_outcome(
        order,
        mode="DEMO",
        forced_scenario="missing_activation_code",
        forced_subscription_id="SUB-1",
        config=TEST_CONFIG,
    )
    assert decision.will_fail is True
    assert decision.failure_subscription_id == "SUB-1"
    assert decision.scenario == "missing_activation_code"


def test_demo_mode_requires_scenario_and_subscription_id():
    order = _make_core_telco_order()
    with pytest.raises(ValueError):
        determine_outcome(order, mode="DEMO", config=TEST_CONFIG)


def test_demo_mode_flags_non_fetchable_scenario():
    order = _make_vas_order()
    decision = determine_outcome(
        order,
        mode="DEMO",
        forced_scenario="region_lock",
        forced_subscription_id="SUB-2",
        config=TEST_CONFIG,
    )
    assert decision.is_non_fetchable is True


def test_realistic_mode_vas_scenario_pool_used_for_vas_subscription():
    order = _make_vas_order()
    decision = determine_outcome(order, mode="REALISTIC", config=TEST_CONFIG)
    assert decision.will_fail is True
    assert decision.scenario in TEST_CONFIG["scenario_pools"]["vas"]


def test_unknown_mode_raises():
    order = _make_core_telco_order()
    with pytest.raises(ValueError):
        determine_outcome(order, mode="BOGUS", config=TEST_CONFIG)


def test_foldable_esim_quirk_only_selected_for_foldable_devices():
    order = Order(order_id="ORD-3", customer_id="CUST-3", order_category=OrderCategory.NEW_CONNECTION)
    order.subscriptions.append(
        Subscription(
            order_id="ORD-3",
            subscription_id="SUB-3",
            subscription_category=SubscriptionCategory.CORE_TELCO,
            subscription_type="Device Purchase/Financing",
            provider="Device Inventory",
            device_category=DeviceCategory.STANDARD,  # NOT foldable
            financing_type=FinancingType.FULL_PAYMENT,
        )
    )
    for _ in range(20):
        decision = determine_outcome(order, mode="REALISTIC", config=TEST_CONFIG)
        assert decision.scenario != "foldable_esim_quirk"
        assert decision.scenario != "trade_in_valuation_mismatch"
