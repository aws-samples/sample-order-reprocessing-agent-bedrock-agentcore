"""
Order History tab — logic functions + Streamlit rendering. Full chronological
lifecycle per order, per FR-22/FR-23, reading Unit 1's OrderProcessingHistory.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from mock_backends.repository import history_repository, orders_repository


def get_order_history(order_id: str) -> list[dict[str, Any]]:
    """Testable logic function."""
    events = history_repository.query_history_for_order(order_id)
    return [
        {
            "timestamp": e.event_timestamp, "event_type": e.event_type.value,
            "tool_name": e.tool_name, "summary": e.summary,
            "resulting_status": e.resulting_status, "subscription_id": e.subscription_id,
            "details": e.details,
        }
        for e in events
    ]


def _render_event_details(event: dict[str, Any]) -> None:
    """Real gap found while demoing: the `details` field (which contains the
    actual answer to "which field was missing and how was it resolved") was
    being silently discarded — only `summary` was ever rendered. Each event
    type has a differently-shaped `details` dict (per Unit 2's tools), so
    this renders the useful parts of each shape explicitly rather than
    dumping raw JSON, which would not be presentable to a non-technical
    audience."""
    details = event.get("details") or {}

    if event["event_type"] == "VALIDATED" and details.get("missing_items"):
        st.markdown("&nbsp;&nbsp;**Missing fields found:**")
        for item in details["missing_items"]:
            st.markdown(
                f"&nbsp;&nbsp;&nbsp;&nbsp;• `{item['missing_field']}` "
                f"— to be fetched from **{item['fetch_from']}**"
            )

    elif event["event_type"] == "FETCHED_DATA":
        field = details.get("field", "?")
        success = details.get("success")
        retry = details.get("retry_attempt", 0)
        retry_note = f" (retry {retry})" if retry else ""
        status_word = "✅ succeeded" if success else "❌ failed"
        st.markdown(f"&nbsp;&nbsp;Fetch of `{field}`{retry_note}: {status_word}")

    elif event["event_type"] == "BACKEND_ERROR":
        field = details.get("field", "?")
        retry = details.get("retry_attempt", 0)
        st.markdown(f"&nbsp;&nbsp;⚠️ Backend error fetching `{field}` (attempt {retry + 1})")

    elif event["event_type"] == "REPROCESSED":
        downstream = details.get("downstream_response", {})
        idempotent = details.get("idempotent_skip", False)
        note = " (idempotent no-op — already activated, no duplicate resubmission)" if idempotent else ""
        if downstream.get("message"):
            st.markdown(f"&nbsp;&nbsp;{downstream['message']}{note}")

    elif event["event_type"] == "ESCALATED":
        if details.get("agent_reasoning"):
            st.markdown(f"&nbsp;&nbsp;**Agent's reasoning:** {details['agent_reasoning']}")
        if details.get("attempted_fixes"):
            st.markdown("&nbsp;&nbsp;**What the agent tried before escalating:**")
            for fix in details["attempted_fixes"]:
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• {fix}")
        if details.get("ticket_id"):
            st.markdown(f"&nbsp;&nbsp;**Ticket created:** `{details['ticket_id']}`")


def render() -> None:
    st.subheader("Order Processing History")

    orders = orders_repository.scan_all_orders()
    if not orders:
        st.info("No orders available yet.")
        return

    # Sort most-recent-first so newly-placed demo/test orders are easy to
    # find, rather than buried in an unordered scan result alongside 100+
    # seeded orders. Real gap found while demoing: scan_all_orders() has no
    # inherent order, making it painful to locate a just-placed order in a
    # long dropdown.
    orders_sorted = sorted(orders, key=lambda o: o.created_at, reverse=True)
    order_labels = [f"{o.order_id} — {o.status.value} — {o.created_at}" for o in orders_sorted]
    order_id_by_label = {label: o.order_id for label, o in zip(order_labels, orders_sorted)}

    selected_label = st.selectbox(
        "Select order for full history (most recent first)",
        order_labels,
        key="history-order-select",
    )
    selected_order_id = order_id_by_label[selected_label]

    history = get_order_history(selected_order_id)
    if not history:
        st.info("No history recorded for this order yet.")
        return

    for event in history:
        sub_label = f" ({event['subscription_id']})" if event["subscription_id"] else ""
        st.markdown(
            f"**{event['timestamp']}** — `{event['event_type']}`{sub_label} — "
            f"{event['summary']} (via {event['tool_name']})"
        )
        _render_event_details(event)
