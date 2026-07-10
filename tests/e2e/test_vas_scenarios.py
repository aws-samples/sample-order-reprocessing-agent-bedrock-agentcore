"""
E2E VAS scenarios (requirements.md Section 7, scenarios 6-9).

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


class TestVasScenarios:
    def test_scenario_6_entitlement_failure_auto_resolves(
        self, lambda_client, crm_orders_table, crm_order_subscriptions_table
    ):
        placed = place_demo_order(
            lambda_client,
            customer_id=_unique_customer_id(),
            vas_selections=["Netflix"],
            forced_scenario="entitlement_failure",
            forced_subscription_type="Netflix",
        )
        assert placed.initial_outcome == "WILL_FAIL"

        final_order = poll_until_terminal(crm_orders_table, placed.order_id)
        assert final_order["status"] == "ACTIVATED", (
            "entitlement_failure is fetchable/fixable per FR-9's CheckVASEligibility "
            "classification (non_fetchable_scenarios in failure_probabilities.json "
            "does NOT include entitlement_failure) — should auto-resolve via partner API retry"
        )
        sub = get_subscription(crm_order_subscriptions_table, placed.order_id, placed.failure_subscription_id)
        assert sub["status"] == "ACTIVATED"

    def test_scenario_7_region_lock_escalates_immediately_without_fetch(
        self, lambda_client, crm_orders_table, crm_order_subscriptions_table, order_processing_history_table
    ):
        placed = place_demo_order(
            lambda_client,
            customer_id=_unique_customer_id(),
            vas_selections=["Disney+"],
            forced_scenario="region_lock",
            forced_subscription_type="Disney+",
        )
        assert placed.initial_outcome == "WILL_FAIL"

        final_order = poll_until_terminal(crm_orders_table, placed.order_id)
        assert final_order["status"] in ("ESCALATED", "PARTIALLY_ACTIVATED"), (
            "region_lock is a hard business-rule block per FR-9/BR-9 "
            "(listed in failure_probabilities.json's non_fetchable_scenarios) — "
            "must escalate, never auto-resolve via fetch"
        )

        history = get_history_events(order_processing_history_table, placed.order_id)
        fetch_events = [
            e for e in history
            if e["event_type"] == "FETCHED_DATA" and e.get("subscription_id") == placed.failure_subscription_id
        ]
        assert not fetch_events, (
            "FR-9/BR-9: CheckVASEligibility should recommend ESCALATE immediately for "
            "region_lock — no FetchMissingData attempt should have been made for this subscription"
        )
        escalate_events = [e for e in history if e["event_type"] == "ESCALATED"]
        assert escalate_events, "Expected an ESCALATED history event (FR-22/FR-24)"

    def test_scenario_8_billing_profile_missing_fetched_and_resubmitted(
        self, lambda_client, crm_orders_table, crm_order_subscriptions_table
    ):
        placed = place_demo_order(
            lambda_client,
            customer_id=_unique_customer_id(),
            vas_selections=["Spotify"],
            forced_scenario="billing_profile_missing",
            forced_subscription_type="Spotify",
        )
        final_order = poll_until_terminal(crm_orders_table, placed.order_id)
        assert final_order["status"] == "ACTIVATED", (
            "billing_profile_missing is fetchable per FR-9's classification — "
            "should be fetched from Billing DB and resubmitted (FR-8/FR-10)"
        )
        sub = get_subscription(crm_order_subscriptions_table, placed.order_id, placed.failure_subscription_id)
        assert sub["status"] == "ACTIVATED"

    def test_scenario_9_vas_dependency_ordering_retries_rather_than_escalates(
        self, lambda_client, crm_orders_table
    ):
        """Per FR-4/FR-9's dependency-ordering intent: a VAS item with
        depends_on set to a not-yet-active core line should be RETRIED after
        a delay rather than escalated prematurely.

        NOTE (genuine gap found while writing this test, not by inspection):
        `_build_subscriptions()` in service.py never sets `depends_on` on any
        subscription it creates — VAS items are built with no depends_on
        value regardless of order contents. There is currently no code path
        that produces a VAS item actually depending on a core line, so this
        scenario cannot be exercised as originally specified. Marking xfail
        with this reason rather than asserting on behavior that cannot
        currently occur."""
        pytest.xfail(
            "service.py._build_subscriptions() never sets `depends_on` on any "
            "subscription — FR-4's dependency modeling exists in the domain model "
            "(Subscription.depends_on) but nothing in Unit 3's order-creation logic "
            "currently populates it, so dependency-ordering retry behavior (FR-9's "
            "intent) has no exercisable path today. See Unit 6 code-summary.md "
            "'Known Gaps' — recommended fix: extend _build_subscriptions() to set "
            "depends_on for VAS items when device/line provisioning is still pending, "
            "or expose an explicit demo_mode_override hook for this scenario."
        )
