"""
Order Reprocessing Agent — Operator Console (real backend).

Run with: streamlit run src/ui/app.py

Requires local AWS credentials configured with the IAM permissions documented
in aidlc-docs/construction/operator-ui/code/code-summary.md.
"""

from __future__ import annotations

import streamlit as st

from ui.mode_detection import get_operating_mode
from ui.tabs import agent_trace, issues, order_history, order_summary, trigger

st.set_page_config(page_title="Order Reprocessing Agent", layout="wide", page_icon="📱")

st.title("📱 Order Reprocessing Agent — Operator Console")
st.caption("Amazon Bedrock AgentCore · Amdocs BSS Reference Implementation")

with st.sidebar:
    st.markdown("### Deployment Info")
    mode = get_operating_mode()
    st.markdown(f"**Mode**: `{mode}`")
    st.caption(
        "Realistic Mode: failures occur probabilistically based on order contents.\n\n"
        "Demo Mode: failures can be explicitly forced from the Trigger tab, for workshop use."
    )

tab_trigger, tab_summary, tab_issues, tab_trace, tab_history = st.tabs(
    ["🛒 Trigger", "📋 Order Summary", "⚠️ Issues", "🔍 Agent Trace", "🕘 Order History"]
)

with tab_trigger:
    trigger.render()

with tab_summary:
    order_summary.render()

with tab_issues:
    issues.render()

with tab_trace:
    agent_trace.render()

with tab_history:
    order_history.render()
