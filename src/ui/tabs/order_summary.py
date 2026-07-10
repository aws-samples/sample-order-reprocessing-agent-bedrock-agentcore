"""
Order Summary tab — logic functions (testable) + Streamlit rendering.
Fresh-fetch on every render, per Q3: A.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from mock_backends.repository import orders_repository, subscriptions_repository

_STATUS_ICONS = {
    "ACTIVATED": "🟢", "PENDING": "⚪", "FAILED": "🔴",
    "PARTIALLY_ACTIVATED": "🟡", "ESCALATED": "🟠",
}  # BR-34


def get_all_orders_summary() -> list[dict[str, Any]]:
    """Testable logic function: fetches all orders with their subscription counts,
    sorted most-recent-first (real demo-usability gap found: scan_all_orders()
    has no inherent order, making a just-placed test order hard to find among
    100+ seeded orders)."""
    orders = orders_repository.scan_all_orders()
    orders_sorted = sorted(orders, key=lambda o: o.created_at, reverse=True)
    return [
        {
            "order_id": o.order_id, "customer_id": o.customer_id,
            "order_category": o.order_category.value, "status": o.status.value,
            "created_at": o.created_at,
        }
        for o in orders_sorted
    ]


def get_order_detail(order_id: str) -> list[dict[str, Any]]:
    """Testable logic function: fetches subscription detail for one order."""
    subs = subscriptions_repository.query_subscriptions_for_order(order_id)
    return [s.to_item() for s in subs]


def render() -> None:
    st.subheader("All Orders")
    orders = get_all_orders_summary()

    if not orders:
        st.info("No orders found yet. Place an order in the Trigger tab, or wait for ambient activity.")
        return

    # Real demo-usability gap found: with 100+ seeded orders, rendering every
    # order as an expander made it very hard to find a just-placed test
    # order. Added a search box (by order_id or customer_id) and capped the
    # default display count, with an option to show all.
    search = st.text_input("Search by order ID or customer ID", key="order-summary-search")
    if search:
        orders = [
            o for o in orders
            if search.lower() in o["order_id"].lower() or search.lower() in o["customer_id"].lower()
        ]

    show_all = st.checkbox(f"Show all {len(orders)} matching orders", value=False, key="order-summary-show-all")
    display_orders = orders if show_all else orders[:20]
    if not show_all and len(orders) > 20:
        st.caption(f"Showing 20 most recent of {len(orders)} orders. Check the box above to see all.")

    for order in display_orders:
        icon = _STATUS_ICONS.get(order["status"], "")
        with st.expander(f"{icon} **{order['order_id']}** — {order['order_category']} — {order['status']}"):
            st.write(f"Customer: {order['customer_id']}")
            st.write(f"Created: {order['created_at']}")
            subs = get_order_detail(order["order_id"])
            for sub in subs:
                sub_icon = _STATUS_ICONS.get(sub.get("status", ""), "")
                is_superseded = sub.get("status") == "SUPERSEDED"
                label = f"{sub_icon} {sub['subscription_type']} — {sub['status']}"
                if is_superseded:  # BR-35: visually de-emphasized
                    st.caption(f"~~{label}~~ (superseded)")
                else:
                    st.write(label)
