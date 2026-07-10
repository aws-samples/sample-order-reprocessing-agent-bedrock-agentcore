"""
E2E Device/Handset scenarios (requirements.md Section 7, scenarios 11-14).

Requires a REAL deployed stack with `operatingMode=DEMO`. Run via:
pytest tests/e2e/ -m e2e
"""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.conftest import get_history_events, get_subscription, place_demo_order, poll_until_terminal

pytestmark = pytest.mark.e2e


def _unique_customer_id() -> str:
    return f"CUST-E2E-{uuid.uuid4().hex[:8].upper()}"


_STANDARD_DEVICE = {
    "device_model": "Galaxy S24",
    "device_category": "Standard",
    "financing_type": "Full Payment",
    "esim_compatible": True,
}

_FOLDABLE_DEVICE = {
    "device_model": "Galaxy Z Fold 6",
    "device_category": "Foldable",
    "financing_type": "Full Payment",
    "esim_compatible": True,
}

_TRADE_IN_DEVICE = {
    "device_model": "iPhone 16 Pro Max",
    "device_category": "Flagship",
    "financing_type": "Trade-in + Installment",
    "esim_compatible": True,
}


class TestDeviceScenarios:
    def test_scenario_11_imei_validation_failure_auto_resolves(
        self, lambda_client, crm_orders_table, crm_order_subscriptions_table
    ):
        placed = place_demo_order(
            lambda_client,
            customer_id=_unique_customer_id(),
            device_selection=_STANDARD_DEVICE,
            forced_scenario="imei_validation_failure",
            forced_subscription_type="Device Purchase/Financing",
        )
        final_order = poll_until_terminal(crm_orders_table, placed.order_id)
        assert final_order["status"] == "ACTIVATED", (
            "imei_validation_failure should be fetched/verified from mock IMEI "
            "Registry and auto-resolved (FR-26)"
        )
        sub = get_subscription(crm_order_subscriptions_table, placed.order_id, placed.failure_subscription_id)
        assert sub["status"] == "ACTIVATED"

    def test_scenario_12_stock_backorder_causes_partial_activation(
        self, lambda_client, crm_orders_table, crm_order_subscriptions_table
    ):
        placed = place_demo_order(
            lambda_client,
            customer_id=_unique_customer_id(),
            device_selection=_STANDARD_DEVICE,
            forced_scenario="stock_backorder",
            forced_subscription_type="Device Purchase/Financing",
        )
        final_order = poll_until_terminal(crm_orders_table, placed.order_id)
        assert final_order["status"] == "PARTIALLY_ACTIVATED", (
            "FR-26: stock/inventory backorder should leave the hardware subscription "
            "item FAILED/PENDING while other items (line) proceed independently — "
            "order should reach PARTIALLY_ACTIVATED, not ACTIVATED or ESCALATED"
        )

        # The device item itself should NOT be ACTIVATED (still blocked on stock).
        device_sub = get_subscription(crm_order_subscriptions_table, placed.order_id, placed.failure_subscription_id)
        assert device_sub["status"] != "ACTIVATED"

        # The mobile line item (a separate subscription in the same order) should
        # have proceeded to ACTIVATED independently, per FR-26's "other items
        # proceed independently" requirement.
        line_subs = [sid for sid in placed.subscription_ids if sid != placed.failure_subscription_id]
        assert line_subs, "Expected a separate Mobile Line subscription alongside the device item"
        line_sub = get_subscription(crm_order_subscriptions_table, placed.order_id, line_subs[0])
        assert line_sub["status"] == "ACTIVATED", (
            "Mobile Line item should activate independently of the backordered device item (FR-26)"
        )

    def test_scenario_13_foldable_esim_quirk_distinct_resolution_path(
        self, lambda_client, crm_orders_table, crm_order_subscriptions_table, order_processing_history_table
    ):
        placed = place_demo_order(
            lambda_client,
            customer_id=_unique_customer_id(),
            device_selection=_FOLDABLE_DEVICE,
            forced_scenario="foldable_esim_quirk",
            forced_subscription_type="Device Purchase/Financing",
        )
        final_order = poll_until_terminal(crm_orders_table, placed.order_id)
        assert final_order["status"] == "ACTIVATED", (
            "foldable_esim_quirk should be resolved via a distinct fetch/resolution "
            "path from standard-phone eSIM handling (FR-26)"
        )
        sub = get_subscription(crm_order_subscriptions_table, placed.order_id, placed.failure_subscription_id)
        assert sub["status"] == "ACTIVATED"
        assert sub.get("device_category") == "Foldable"

        history = get_history_events(order_processing_history_table, placed.order_id)
        assert any(
            e["event_type"] in ("FETCHED_DATA", "REPROCESSED") and e.get("subscription_id") == placed.failure_subscription_id
            for e in history
        ), "Expected at least one fetch/reprocess history event for the foldable device item (FR-24)"

    def test_scenario_14_trade_in_valuation_mismatch_escalates_immediately(
        self, lambda_client, crm_orders_table, order_processing_history_table
    ):
        placed = place_demo_order(
            lambda_client,
            customer_id=_unique_customer_id(),
            device_selection=_TRADE_IN_DEVICE,
            forced_scenario="trade_in_valuation_mismatch",
            forced_subscription_type="Device Purchase/Financing",
        )
        assert placed.initial_outcome == "WILL_FAIL"

        final_order = poll_until_terminal(crm_orders_table, placed.order_id)
        assert final_order["status"] in ("ESCALATED", "PARTIALLY_ACTIVATED"), (
            "trade_in_valuation_mismatch is a hard business-rule block per FR-26 "
            "(listed in failure_probabilities.json's non_fetchable_scenarios) — "
            "must escalate immediately, same pattern as VAS region-lock (FR-9)"
        )

        history = get_history_events(order_processing_history_table, placed.order_id)
        fetch_events = [
            e for e in history
            if e["event_type"] == "FETCHED_DATA" and e.get("subscription_id") == placed.failure_subscription_id
        ]
        assert not fetch_events, (
            "No fetch attempt should be made for trade_in_valuation_mismatch — "
            "it's a hard business-rule block, not a fetchable field (FR-26)"
        )
