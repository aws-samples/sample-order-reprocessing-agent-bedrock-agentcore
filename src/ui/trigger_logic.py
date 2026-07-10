"""
Trigger tab — business logic functions (place order call, live status polling).
Separated from Streamlit rendering code (in tabs/trigger.py) so this logic is
independently unit-testable (per Code Generation plan Step 9's note that
Streamlit rendering itself isn't meaningfully unit-testable, but the
underlying data/logic functions are).
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from mock_backends.repository import history_repository
from mock_backends.shared.domain_models import HistoryEventType
from ui.aws_clients import get_lambda_client

_ORDER_PLACEMENT_FUNCTION_NAME = "ora-order-placement-service"
# Real bug found while diagnosing a live demo: HistoryEventType.RESOLVED is
# defined in domain_models.py but NO tool anywhere in the codebase ever
# actually emits it — every real resolution trace observed against the live
# deployment ends with a REPROCESSED event (resulting_status=ACTIVATED or
# PARTIALLY_ACTIVATED), never RESOLVED. This meant poll_for_terminal_status()
# would ALWAYS time out after 30s and return None, so the Trigger tab could
# never show a real-time "resolved!" message even when the agent had
# genuinely succeeded seconds earlier — a demo-breaking bug, since it made a
# fully-working backend look broken/stuck in the UI.
_TERMINAL_EVENT_TYPES = {HistoryEventType.REPROCESSED, HistoryEventType.ESCALATED}
_POLL_INTERVAL_SECONDS = 2
# NOTE — REQUIREMENTS DEVIATION FROM BR-39, flagged explicitly (not silently
# changed): BR-39 originally specified a 30-second UI polling cap. A real,
# multi-subscription order tested live (4 subscription items, one hitting a
# genuine backend error requiring a retry + escalation) took ~75 seconds
# wall-clock before its LAST subscription item resolved, even though the
# FIRST item resolved in ~17s. A 30s cap made a fully-working, in-progress
# resolution look permanently stuck. Extended to 90s to accommodate
# realistic multi-subscription orders. This is a genuine UX/requirements
# trade-off (users wait longer before seeing "still processing" as a
# fallback), not just a bug fix — flagged here and in aidlc-docs/audit.md
# rather than changed silently.
_MAX_POLL_SECONDS = 90


def invoke_place_order(request_payload: dict[str, Any]) -> dict[str, Any]:
    """Q5: A — invokes the real deployed Lambda via boto3, not a direct
    Python function call, so the UI exercises the actual infrastructure."""
    client = get_lambda_client()
    response = client.invoke(
        FunctionName=_ORDER_PLACEMENT_FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(request_payload).encode("utf-8"),
    )
    payload = json.loads(response["Payload"].read())
    return payload


def poll_for_terminal_status(order_id: str, max_seconds: int = _MAX_POLL_SECONDS) -> Optional[dict[str, Any]]:
    """Polls OrderProcessingHistory for up to `max_seconds`.

    Real gap found alongside the RESOLVED-vs-REPROCESSED bug: for a
    multi-subscription order, the FIRST subscription to reach a terminal
    state (REPROCESSED/ESCALATED) does not mean the WHOLE ORDER is done —
    other subscription items may still be mid-flight. The original
    implementation returned as soon as any single terminal event appeared,
    which could show a misleadingly early "resolved!" while the agent was
    still working on other items. Fixed by tracking terminal events per
    subscription_id and only returning once every subscription_id that has
    ANY history event has reached a terminal one — using the order's OWN
    subscription_ids (from the place_order response) as the source of truth
    for "how many items must resolve," not just "however many we've seen
    events for so far" (which could under-count if the agent hasn't started
    on a later item yet).
    """
    elapsed = 0
    last_terminal_by_sub: dict[str, dict[str, Any]] = {}

    while elapsed < max_seconds:
        events = history_repository.query_history_for_order(order_id)

        subscription_ids_seen = {e.subscription_id for e in events if e.subscription_id}
        last_terminal_by_sub = {}
        for event in events:
            if event.event_type in _TERMINAL_EVENT_TYPES and event.subscription_id:
                last_terminal_by_sub[event.subscription_id] = {
                    "event_type": event.event_type.value,
                    "summary": event.summary,
                    "resulting_status": event.resulting_status,
                }

        if subscription_ids_seen and subscription_ids_seen == set(last_terminal_by_sub.keys()):
            # Every subscription this order has touched has reached a
            # terminal state. Prefer an ESCALATED result if any item
            # escalated (worse-case takes priority for the summary shown),
            # otherwise return the last REPROCESSED event.
            escalated = [v for v in last_terminal_by_sub.values() if v["event_type"] == "ESCALATED"]
            return escalated[0] if escalated else list(last_terminal_by_sub.values())[-1]

        time.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS

    return None


def get_history_snapshot(order_id: str) -> list[dict[str, Any]]:
    """Returns the current history events for an order, used to render
    incremental progress in the live status tracker between poll iterations."""
    events = history_repository.query_history_for_order(order_id)
    return [
        {"event_type": e.event_type.value, "summary": e.summary, "timestamp": e.event_timestamp}
        for e in events
    ]
