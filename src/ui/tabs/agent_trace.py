"""
Agent Trace tab — logic functions + Streamlit rendering. Real CloudWatch
Logs Insights query implementation, per Q4: A (code-complete now, even
though no meaningful trace data exists until AgentCore Runtime's agent
loop, currently a placeholder per Unit 2, is implemented).
"""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

from mock_backends.repository import orders_repository
from ui.aws_clients import get_logs_client

_AGENT_RUNTIME_LOG_GROUP = "/aws/bedrock-agentcore/ora-order-reprocessing-agent"
_QUERY_POLL_INTERVAL_SECONDS = 1
_QUERY_MAX_POLL_SECONDS = 15


def query_agent_trace(order_id: str, start_time: int, end_time: int) -> list[dict[str, Any]]:
    """Testable logic function: runs a CloudWatch Logs Insights query scoped
    to the given order_id (used as the AgentCore Runtime session ID, per
    Unit 3's runtime_invoker.py setting runtimeSessionId=order_id)."""
    client = get_logs_client()

    try:
        start_response = client.start_query(
            logGroupName=_AGENT_RUNTIME_LOG_GROUP,
            startTime=start_time,
            endTime=end_time,
            queryString=f"fields @timestamp, @message | filter @message like /{order_id}/ | sort @timestamp asc",
        )
    except client.exceptions.ResourceNotFoundException:
        return []  # log group doesn't exist yet (Runtime placeholder hasn't logged anything)

    query_id = start_response["queryId"]
    elapsed = 0
    while elapsed < _QUERY_MAX_POLL_SECONDS:
        result = client.get_query_results(queryId=query_id)
        if result["status"] == "Complete":
            return [
                {field["field"]: field["value"] for field in row}
                for row in result["results"]
            ]
        # nosemgrep: arbitrary-sleep -- intentional poll interval, not leftover debug code
        time.sleep(_QUERY_POLL_INTERVAL_SECONDS)
        elapsed += _QUERY_POLL_INTERVAL_SECONDS
    return []


def render() -> None:
    st.subheader("Agent Reasoning Trace")

    orders = orders_repository.scan_all_orders()
    if not orders:
        st.info("No orders available yet.")
        return

    order_ids = [o.order_id for o in orders]
    selected_order_id = st.selectbox("Select order", order_ids, key="trace-order-select")

    if st.button("Load Trace", key="trace-load-button"):
        now = int(time.time())
        thirty_days_ago = now - (30 * 24 * 60 * 60)
        with st.spinner("Querying CloudWatch Logs Insights..."):
            rows = query_agent_trace(selected_order_id, thirty_days_ago, now)

        if not rows:
            st.info(
                "No trace data found for this order. Note: the AgentCore Runtime's "
                "agent loop is currently a placeholder (see Unit 2's known follow-ups) "
                "— no real reasoning traces will exist until that is implemented."
            )
        else:
            for row in rows:
                st.text(f"[{row.get('@timestamp', '')}] {row.get('@message', '')}")
