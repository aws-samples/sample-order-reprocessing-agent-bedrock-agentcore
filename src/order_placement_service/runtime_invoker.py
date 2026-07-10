"""
Runtime invoker — bridges Unit 2's EventBridge rule (OrderStatusChanged) to
AgentCore Runtime, since Runtime does not yet have a native EventBridge
target construct at the currently pinned CDK version.

This closes the gap explicitly flagged in Unit 2's code-summary.md (gap #3:
"EventBridge rule has no invocation target yet ... deferred to Unit 3's
ownership of the Order Placement Service → EventBridge → Runtime hand-off").

Uses boto3's bedrock-agentcore client's InvokeAgentRuntime operation
(verified present via direct botocore service-model inspection before writing
this code).
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3


def _build_runtime_session_id(order_id: str) -> str:
    """AgentCore Runtime's InvokeAgentRuntime requires runtimeSessionId to be
    33-256 characters (verified via direct botocore service-model
    introspection: `min: 33, max: 256, pattern: None`). order_id alone
    (format "ORD-XXXXXXXX", ~12 chars) is too short — this was a REAL bug
    found only by testing a real failure-triggered agent invocation against
    the live deployment: every invocation failed with ParamValidationError
    ("Invalid length for parameter runtimeSessionId, value: 12, valid min
    length: 33"), silently retried by EventBridge's automatic Lambda retry
    policy with no visible effect on the order (it stayed FAILED forever).
    Fixed by prefixing with a fixed string to guarantee length while keeping
    the session ID traceable back to the order (useful for the Agent Trace
    tab's CloudWatch Logs Insights queries, which correlate by order_id)."""
    session_id = f"ora-order-reprocessing-session-{order_id}"
    return session_id.ljust(33, "-")


def invoke_runtime(event_detail: dict[str, Any]) -> dict[str, Any]:
    """Called with the EventBridge event's `detail` payload
    (order_id, status, failed_subscriptions — per Unit 3's
    domain-entities.md EventBridge Event Shape)."""
    runtime_arn = os.environ["AGENT_RUNTIME_ARN"]
    region = os.environ.get("AWS_REGION", "eu-west-2")

    client = boto3.client("bedrock-agentcore", region_name=region)
    response = client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn,
        runtimeSessionId=_build_runtime_session_id(event_detail["order_id"]),
        payload=json.dumps(event_detail).encode("utf-8"),
        contentType="application/json",
        accept="application/json",
    )
    return {"order_id": event_detail["order_id"], "invoked": True, "status_code": response.get("statusCode")}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. Expects the raw EventBridge event — extracts `detail`."""
    return invoke_runtime(event["detail"])
