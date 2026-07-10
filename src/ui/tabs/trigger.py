"""
Trigger tab — Streamlit rendering. Real backend wiring (per Q5: A, boto3
Lambda invoke) replacing the earlier ui_mockup.py's simulated random logic.
"""

from __future__ import annotations

import streamlit as st

from ui.mode_detection import get_operating_mode
from ui.trigger_logic import get_history_snapshot, invoke_place_order, poll_for_terminal_status

_DEVICE_MODELS = ["iPhone 16 Pro Max", "Samsung Galaxy Z Fold 6", "Samsung Galaxy S24"]
_FINANCING_TYPES = ["Full Payment", "Installment-12mo", "Installment-24mo", "Trade-in + Installment"]
_PLANS = ["POST5G999", "POST5G050", "PRE0BASIC"]
_VAS_OPTIONS = ["Netflix", "Spotify", "Disney+"]
_DEMO_SCENARIOS = [
    "missing_activation_code", "missing_plan_id", "missing_iccid", "missing_msisdn",
    "imei_validation_failure", "stock_backorder", "foldable_esim_quirk", "trade_in_valuation_mismatch",
    "entitlement_failure", "region_lock", "billing_profile_missing",
]


def render() -> None:
    st.subheader("Place a New Order")
    mode = get_operating_mode()
    st.caption(f"Deployment mode: **{mode}**")

    col1, col2 = st.columns(2)
    with col1:
        order_category = st.selectbox(
            "Order Category", ["New Connection", "Upgrade", "Add Subscription"],
            key="trigger-order-category",
        )
        customer_id = st.text_input("Customer ID", value="CUST-00001", key="trigger-customer-id")

        device_model = financing_type = None
        if order_category != "Add Subscription":
            device_model = st.selectbox("Device", _DEVICE_MODELS, key="trigger-device-model")
            financing_type = st.selectbox("Financing Type", _FINANCING_TYPES, key="trigger-financing-type")

    with col2:
        plan_id = st.selectbox("Plan", _PLANS, key="trigger-plan-id")
        st.markdown("**Add Value-Added Services**")
        vas_selections = [vas for vas in _VAS_OPTIONS if st.checkbox(vas, key=f"trigger-vas-{vas}")]

    forced_scenario = None
    if mode == "DEMO":
        # BR-38: primary, visible control in Demo Mode — not hidden behind "advanced"
        st.divider()
        st.markdown("### 🎯 Demo Mode — Force a Scenario")
        forced_scenario = st.selectbox("Scenario to force", _DEMO_SCENARIOS, key="trigger-forced-scenario")

    if st.button("🛒 Place Order", type="primary", key="trigger-submit"):
        device_selection = None
        if device_model is not None:
            device_selection = {
                "device_model": device_model,
                "device_category": "Foldable" if "Fold" in device_model else "Standard",
                "financing_type": financing_type,
            }

        payload = {
            "customer_id": customer_id,
            "order_category": order_category,
            "plan_id": plan_id,
            "device_selection": device_selection,
            "vas_selections": vas_selections,
        }
        if mode == "DEMO" and forced_scenario:
            payload["demo_mode_override"] = {
                "forced_scenario": forced_scenario,
                "forced_subscription_type": device_model or "Mobile Line",
            }

        with st.spinner("Placing order..."):
            result = invoke_place_order(payload)

        order_id = result.get("order_id", "UNKNOWN")
        st.success(f"Order **{order_id}** placed.")

        if result.get("initial_outcome") == "WILL_FAIL":
            status_placeholder = st.empty()
            with status_placeholder.container():
                st.warning(f"⚠️ Agent detected an issue: *{result.get('scenario', 'unknown')}*. Resolving...")

            terminal_event = poll_for_terminal_status(order_id)

            with status_placeholder.container():
                if terminal_event is None:
                    st.info("Still processing — check the Order History tab for updates.")
                elif terminal_event["event_type"] == "ESCALATED":
                    st.error(f"🚨 Escalated: {terminal_event['summary']}")
                else:
                    # REPROCESSED is the actual terminal success event emitted
                    # by ReprocessOrder — resulting_status distinguishes full
                    # vs. partial activation (e.g. multi-subscription orders
                    # where one item was fixed but another is still pending).
                    resulting_status = terminal_event.get("resulting_status", "")
                    if resulting_status == "PARTIALLY_ACTIVATED":
                        st.warning(f"🟡 Partially resolved: {terminal_event['summary']}")
                    else:
                        st.success(f"✅ Resolved: {terminal_event['summary']}")

            _render_resolution_flow(order_id, result)
        else:
            st.success("✅ Activated — no issues encountered.")


def _render_resolution_flow(order_id: str, place_order_result: dict) -> None:
    """Real gap found while demoing: the backend genuinely does all of this
    work, but it happens invisibly across 4-5 separate AWS services over
    ~20-30 seconds, with nothing in the UI explaining WHERE each step
    actually happens. This renders the REAL architecture path (not a
    simplified guess) below the live status, using the actual history
    events recorded for this specific order as evidence that each step
    genuinely occurred — not just a static diagram."""
    st.divider()
    st.markdown("### 🔍 How this was resolved — the real flow")

    history = get_history_snapshot(order_id)
    event_types_seen = {e["event_type"] for e in history}

    # nosemgrep: string-concat-in-list -- each description below is one
    # intentional multi-line string literal split for readability, not
    # separate list elements accidentally concatenated.
    steps = [
        ("1️⃣ Order Placement Lambda", "ora-order-placement-service",
         "Writes the order as FAILED to DynamoDB, then fires a real "
         "**EventBridge** event (`OrderStatusChanged`) — NOT a CloudWatch "
         "log scan. EventBridge is used because it's immediate and "
         "guaranteed-delivery, rather than depending on log-polling latency.",
         True),
        ("2️⃣ EventBridge Rule → Runtime Invoker Lambda", "ora-runtime-invoker",
         "A rule matching `OrderStatusChanged` events with `status=FAILED` "
         "triggers a small bridging Lambda, which calls Bedrock AgentCore's "
         "`InvokeAgentRuntime` API to hand the failure details to the agent.",
         True),
        ("3️⃣ AgentCore Runtime — the real agent", "Claude Sonnet 4.6 via Bedrock AgentCore",
         "A real Strands Agent, backed by Claude Sonnet 4.6, receives the "
         "failure details and autonomously decides what to do next — this is "
         "genuine LLM reasoning, not a scripted if/else.",
         "DETECTED" in event_types_seen),
        ("4️⃣ Agent calls its tools", "GetOrderDetails → ValidateOrder → FetchMissingData → ReprocessOrder",
         "Each is a separate, real Lambda function the agent calls via "
         "AgentCore Gateway (MCP). The agent decides which to call and in "
         "what order — visible below in the tool-by-tool trail.",
         "FETCHED_DATA" in event_types_seen or "REPROCESSED" in event_types_seen),
        ("5️⃣ Order re-submitted & re-activated", "ReprocessOrder → mock GVPM (TMF641)",
         "Once the missing data is fetched, the agent resubmits the "
         "corrected subscription item, and the order's status is updated "
         "back in DynamoDB — same table the UI reads from.",
         "REPROCESSED" in event_types_seen),
    ]

    for title, real_component, description, completed in steps:
        icon = "✅" if completed else "⏳"
        st.markdown(f"{icon} **{title}**")
        st.caption(f"Real AWS component: `{real_component}`")
        st.markdown(description)

    st.divider()
    st.markdown("**Tool-by-tool trail for this order** (from `OrderProcessingHistory` — written by the agent's own tools as it acts, not reconstructed afterward):")
    for event in history:
        st.markdown(f"- `{event['event_type']}` — {event['summary']} ({event['timestamp']})")
    st.caption(
        "See the **Order History** tab for the full detail on which fields "
        "were missing, where each was fetched from, and (for escalations) "
        "the agent's full written reasoning."
    )
