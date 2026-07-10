"""
Issues tab — logic functions + Streamlit rendering. Filtered view of
ESCALATED and PARTIALLY_ACTIVATED orders, per FR-19 tab 3.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from mock_backends.repository import orders_repository, subscriptions_repository
from mock_backends.shared.domain_models import OrderStatus


def get_issues() -> list[dict[str, Any]]:
    """Testable logic function: fetches ESCALATED + PARTIALLY_ACTIVATED orders
    via Unit 1's GSI-backed query (query_orders_by_status)."""
    escalated = orders_repository.query_orders_by_status(OrderStatus.ESCALATED)
    partial = orders_repository.query_orders_by_status(OrderStatus.PARTIALLY_ACTIVATED)

    issues = []
    for order in escalated + partial:
        subs = subscriptions_repository.query_subscriptions_for_order(order.order_id)
        failed_subs = [s for s in subs if s.status.value in ("FAILED",)]
        issues.append({
            "order_id": order.order_id,
            "status": order.status.value,
            "failed_subscriptions": [
                {"subscription_id": s.subscription_id, "subscription_type": s.subscription_type,
                 "failure_reason": s.failure_reason}
                for s in failed_subs
            ],
        })
    return issues


def render() -> None:
    st.subheader("Escalated / Partially Activated Orders")
    issues = get_issues()

    if not issues:
        st.success("No open issues — all orders are healthy.")
        return

    for issue in issues:
        with st.container(border=True):
            st.error(f"**{issue['order_id']}** — Status: `{issue['status']}`")
            for sub in issue["failed_subscriptions"]:
                st.write(f"- {sub['subscription_type']} ({sub['subscription_id']}): {sub['failure_reason']}")
