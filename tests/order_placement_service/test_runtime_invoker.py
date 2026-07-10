"""Unit tests for order_placement_service.runtime_invoker.

Uses unittest.mock rather than moto, since moto's bedrock-agentcore support
may be limited/absent — mocking the boto3 client directly is more reliable
for this specific operation.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from order_placement_service.runtime_invoker import _build_runtime_session_id, handler, invoke_runtime


def test_build_runtime_session_id_meets_minimum_length():
    """Real bug found via live deployment testing: AgentCore Runtime's
    InvokeAgentRuntime requires runtimeSessionId to be 33-256 characters
    (verified via botocore service-model introspection). A bare order_id
    (e.g. "ORD-1", "ORD-19984436") is far too short and previously caused
    every real agent invocation to fail with ParamValidationError, silently
    retried by EventBridge with no effect on the order — moto/mocks could
    never have caught this since they don't enforce real API length
    constraints."""
    session_id = _build_runtime_session_id("ORD-1")
    assert len(session_id) >= 33
    assert "ORD-1" in session_id

    # Also verify a longer, more realistic order_id still produces a valid session ID
    session_id_2 = _build_runtime_session_id("ORD-19984436")
    assert len(session_id_2) >= 33
    assert "ORD-19984436" in session_id_2


@patch("order_placement_service.runtime_invoker.boto3.client")
def test_invoke_runtime_calls_bedrock_agentcore(mock_boto_client, monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:eu-west-2:123456789012:runtime/test")

    mock_client = MagicMock()
    mock_client.invoke_agent_runtime.return_value = {"statusCode": 200}
    mock_boto_client.return_value = mock_client

    result = invoke_runtime({"order_id": "ORD-1", "status": "FAILED", "failed_subscriptions": []})

    assert result["order_id"] == "ORD-1"
    assert result["invoked"] is True
    mock_client.invoke_agent_runtime.assert_called_once()
    call_kwargs = mock_client.invoke_agent_runtime.call_args.kwargs
    assert len(call_kwargs["runtimeSessionId"]) >= 33
    assert "ORD-1" in call_kwargs["runtimeSessionId"]
    assert call_kwargs["agentRuntimeArn"] == os.environ["AGENT_RUNTIME_ARN"]


@patch("order_placement_service.runtime_invoker.boto3.client")
def test_handler_extracts_detail_from_eventbridge_event(mock_boto_client, monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:eu-west-2:123456789012:runtime/test")

    mock_client = MagicMock()
    mock_client.invoke_agent_runtime.return_value = {"statusCode": 200}
    mock_boto_client.return_value = mock_client

    eventbridge_event = {
        "source": "crm.orders",
        "detail-type": "OrderStatusChanged",
        "detail": {"order_id": "ORD-2", "status": "FAILED", "failed_subscriptions": []},
    }

    result = handler(eventbridge_event, None)
    assert result["order_id"] == "ORD-2"
