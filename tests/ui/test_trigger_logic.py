"""Unit tests for trigger_logic.py — specifically poll_for_terminal_status(),
which had NO test coverage at all prior to this fix. This gap is exactly why
a real bug (waiting on HistoryEventType.RESOLVED, which nothing ever emits)
went undetected through all of Unit 4's original development and multiple
rounds of local + real-deployment testing — it only surfaced when a user
tried to actually demo the Trigger tab's live status update.

Also covers a second, related gap found in the same live demo session:
the original implementation returned as soon as ANY single subscription
item reached a terminal state, which is misleading for multi-subscription
orders where other items are still being processed by the agent."""

from __future__ import annotations

from mock_backends.repository import history_repository
from mock_backends.shared.domain_models import HistoryEvent, HistoryEventType
from ui.trigger_logic import poll_for_terminal_status


def test_poll_detects_reprocessed_as_terminal_success(dynamodb_tables):
    """Real bug fixed: poll_for_terminal_status() previously waited for
    HistoryEventType.RESOLVED, which is defined in domain_models.py but never
    actually emitted by any tool — every real successful resolution ends with
    a REPROCESSED event (resulting_status=ACTIVATED). The old code would
    always time out and return None even on a genuinely successful
    resolution, making the Trigger tab's live status permanently show "still
    processing" for a fully-working backend."""
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-1", event_type=HistoryEventType.REPROCESSED,
            tool_name="ReprocessOrder", summary="Reprocessed SUB-1: ACTIVATED",
            resulting_status="ACTIVATED", subscription_id="SUB-1",
            event_timestamp="2026-01-01T00:00:05Z",
        )
    )

    result = poll_for_terminal_status("ORD-1", max_seconds=2)
    assert result is not None
    assert result["event_type"] == "REPROCESSED"
    assert result["resulting_status"] == "ACTIVATED"


def test_poll_detects_escalated_as_terminal(dynamodb_tables):
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-2", event_type=HistoryEventType.ESCALATED,
            tool_name="EscalateToHuman", summary="Escalated to human: reason",
            resulting_status="ESCALATED", subscription_id="SUB-1",
            event_timestamp="2026-01-01T00:00:05Z",
        )
    )

    result = poll_for_terminal_status("ORD-2", max_seconds=2)
    assert result is not None
    assert result["event_type"] == "ESCALATED"


def test_poll_returns_none_when_no_terminal_event_within_timeout(dynamodb_tables):
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-3", event_type=HistoryEventType.DETECTED,
            tool_name="GetOrderDetails", summary="Order failed",
            resulting_status="FAILED", event_timestamp="2026-01-01T00:00:01Z",
        )
    )

    result = poll_for_terminal_status("ORD-3", max_seconds=2)
    assert result is None


def test_poll_ignores_non_terminal_events_after_terminal_one_exists(dynamodb_tables):
    """Verifies the scan checks all events for a terminal type, not just the
    latest one by insertion order."""
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-4", event_type=HistoryEventType.DETECTED,
            tool_name="GetOrderDetails", summary="Order failed",
            resulting_status="FAILED", event_timestamp="2026-01-01T00:00:01Z",
        )
    )
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-4", event_type=HistoryEventType.REPROCESSED,
            tool_name="ReprocessOrder", summary="Reprocessed SUB-1: ACTIVATED",
            resulting_status="ACTIVATED", subscription_id="SUB-1",
            event_timestamp="2026-01-01T00:00:05Z",
        )
    )

    result = poll_for_terminal_status("ORD-4", max_seconds=2)
    assert result is not None
    assert result["event_type"] == "REPROCESSED"


def test_poll_waits_for_all_subscriptions_in_multi_item_order(dynamodb_tables):
    """Real gap found via a live demo: a 4-subscription order where the
    FIRST item resolved in ~17s but the agent was still working on other
    items for another ~60s. The old implementation would have returned
    immediately on the first REPROCESSED event, showing a misleading early
    "resolved!" while 3 other items were still mid-flight. This test locks
    in that poll_for_terminal_status() waits until EVERY subscription_id
    that has any history event has reached a terminal state."""
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-5", event_type=HistoryEventType.REPROCESSED,
            tool_name="ReprocessOrder", summary="Reprocessed SUB-1: ACTIVATED",
            resulting_status="PARTIALLY_ACTIVATED", subscription_id="SUB-1",
            event_timestamp="2026-01-01T00:00:05Z",
        )
    )
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-5", event_type=HistoryEventType.VALIDATED,
            tool_name="ValidateOrder", summary="Validation found 1 missing field(s)",
            resulting_status="FAILED", subscription_id="SUB-2",
            event_timestamp="2026-01-01T00:00:06Z",
        )
    )

    result = poll_for_terminal_status("ORD-5", max_seconds=2)
    assert result is None, "Should not report done while SUB-2 is still non-terminal"


def test_poll_returns_result_once_all_subscriptions_terminal(dynamodb_tables):
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-6", event_type=HistoryEventType.REPROCESSED,
            tool_name="ReprocessOrder", summary="Reprocessed SUB-1: ACTIVATED",
            resulting_status="PARTIALLY_ACTIVATED", subscription_id="SUB-1",
            event_timestamp="2026-01-01T00:00:05Z",
        )
    )
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-6", event_type=HistoryEventType.ESCALATED,
            tool_name="EscalateToHuman", summary="Escalated to human: backend error",
            resulting_status="ESCALATED", subscription_id="SUB-2",
            event_timestamp="2026-01-01T00:00:10Z",
        )
    )

    result = poll_for_terminal_status("ORD-6", max_seconds=2)
    assert result is not None
    assert result["event_type"] == "ESCALATED"
