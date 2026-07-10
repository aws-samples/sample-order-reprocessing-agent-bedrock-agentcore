"""
E2E idempotency test (requirements.md Section 7, scenario 10 / FR-21).

Requires a REAL deployed stack with `operatingMode=DEMO`. Run via:
pytest tests/e2e/ -m e2e
"""

from __future__ import annotations

import json
import uuid

import boto3
import pytest

from tests.e2e.conftest import REGION, get_history_events, get_subscription, place_demo_order, poll_until_terminal

pytestmark = pytest.mark.e2e


def _unique_customer_id() -> str:
    return f"CUST-E2E-{uuid.uuid4().hex[:8].upper()}"


class TestIdempotency:
    def test_scenario_10_duplicate_reprocess_does_not_double_submit(
        self, lambda_client, crm_orders_table, crm_order_subscriptions_table, order_processing_history_table
    ):
        """FR-21: ReprocessOrder must use conditional writes/idempotency to
        prevent duplicate submission on retry/redelivery.

        This test can't easily force a genuine duplicate EventBridge delivery
        from outside (that's an AWS-internal at-least-once delivery behavior,
        not something a test can directly trigger deterministically). Instead,
        it validates the invariant FR-21 depends on directly: invoking the
        ReprocessOrder tool's underlying repository operation twice in a row
        for the same subscription should NOT result in two REPROCESSED history
        events or a second downstream resubmission — this is exactly what
        Unit 1's subscriptions_repository.transition_status_idempotent()
        (the idempotency guard referenced throughout Units 1/3's code-summaries)
        is designed to prevent."""
        placed = place_demo_order(
            lambda_client,
            customer_id=_unique_customer_id(),
            forced_scenario="missing_activation_code",
            forced_subscription_type="Mobile Line",
        )
        final_order = poll_until_terminal(crm_orders_table, placed.order_id)
        assert final_order["status"] == "ACTIVATED"

        history_after_first_resolution = get_history_events(order_processing_history_table, placed.order_id)
        reprocess_events_before = [
            e for e in history_after_first_resolution
            if e["event_type"] == "REPROCESSED" and e.get("subscription_id") == placed.failure_subscription_id
        ]
        assert len(reprocess_events_before) >= 1, "Expected at least one REPROCESSED event from the normal flow"

        # Simulate a duplicate EventBridge redelivery by re-invoking the Runtime
        # Invoker Lambda directly with the SAME order_id/failed_subscriptions
        # payload shape that service.py's _fire_order_status_changed_event()
        # originally sent — this mimics EventBridge's documented at-least-once
        # delivery semantics without needing to wait for a real duplicate.
        events_client = boto3.client("events", region_name=REGION)
        events_client.put_events(
            Entries=[
                {
                    "Source": "crm.orders",
                    "DetailType": "OrderStatusChanged",
                    "Detail": json.dumps(
                        {
                            "order_id": placed.order_id,
                            "status": "FAILED",
                            "failed_subscriptions": [
                                {
                                    "subscription_id": placed.failure_subscription_id,
                                    "scenario": placed.scenario,
                                    "is_non_fetchable": False,
                                }
                            ],
                        }
                    ),
                }
            ]
        )

        # Give the duplicate delivery time to be processed (or correctly no-op).
        import time

        time.sleep(15)

        sub = get_subscription(crm_order_subscriptions_table, placed.order_id, placed.failure_subscription_id)
        assert sub["status"] == "ACTIVATED", (
            "Subscription should remain ACTIVATED after the duplicate event — "
            "transition_status_idempotent()'s allowed_current_statuses guard "
            "(Unit 1) should reject the no-op duplicate transition attempt"
        )

        history_after_duplicate = get_history_events(order_processing_history_table, placed.order_id)
        reprocess_events_after = [
            e for e in history_after_duplicate
            if e["event_type"] == "REPROCESSED" and e.get("subscription_id") == placed.failure_subscription_id
        ]
        assert len(reprocess_events_after) == len(reprocess_events_before), (
            f"FR-21 VIOLATION: expected no additional REPROCESSED events from the "
            f"duplicate delivery, but count went from {len(reprocess_events_before)} "
            f"to {len(reprocess_events_after)} — this would mean a duplicate resubmission "
            f"to the mock GVPM/VAS adapter occurred, which is exactly what FR-21 prohibits"
        )
