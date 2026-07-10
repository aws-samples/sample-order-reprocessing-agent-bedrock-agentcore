"""
Gateway tool pool — connects to Unit 2's AgentCore Gateway MCP endpoint
(gateway_url, from agent_orchestration.py's Gateway construct) and exposes
the 6 registered tools (GetOrderDetails, ValidateOrder, FetchMissingData,
CheckVASEligibility, ReprocessOrder, EscalateToHuman) to the Strands Agent.

Follows the standard Strands + AgentCore Gateway integration pattern:
MCPClient wrapping mcp's streamablehttp_client, SigV4-signed per Gateway's
IamAuthorizer configuration.
"""

from __future__ import annotations

import os

from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp import MCPClient

from sigv4_auth import SigV4HTTPAuth


def _make_gateway_client() -> MCPClient:
    gateway_url = os.environ["GATEWAY_URL"]
    region = os.environ.get("AWS_REGION", "eu-west-2")
    auth = SigV4HTTPAuth(region=region)

    return MCPClient(
        lambda: streamablehttp_client(
            url=gateway_url,
            headers={"Accept": "application/json, text/event-stream"},
            auth=auth,
        )
    )


def get_gateway_client() -> MCPClient:
    """Returns a fresh MCPClient for the Gateway MCP endpoint. Callers are
    expected to use this as a context manager (`with get_gateway_client() as
    client:`) so the underlying HTTP session is properly closed, per
    MCPClient's documented usage pattern."""
    return _make_gateway_client()
