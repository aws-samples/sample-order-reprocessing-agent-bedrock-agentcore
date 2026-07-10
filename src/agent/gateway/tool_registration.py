"""
AgentCore Gateway tool registration — maps the 6 agent tool Lambdas to
MCP-compatible tool schemas for Gateway registration.

Per infrastructure-design.md's Service Mapping (AgentCore Gateway), and each
tool's handler signature (agent/tools/*.py).
"""

from __future__ import annotations

# Tool schemas follow the MCP tool definition shape: name, description,
# input schema (JSON Schema), mapped to the corresponding Lambda function
# (referenced by logical construct ID here; wired to real ARNs in CDK,
# see infrastructure/cdk_constructs/agent_tools.py).

TOOL_DEFINITIONS = [
    {
        "name": "GetOrderDetails",
        "description": "Fetches the full order record and all associated subscription items from the CRM.",
        "lambda_construct_id": "GetOrderDetailsTool",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "ValidateOrder",
        "description": "Checks which required fields are missing across subscription items. Operates "
                        "on data already fetched by GetOrderDetails — pass that output directly "
                        "rather than re-fetching.",
        "lambda_construct_id": "ValidateOrderTool",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "customer_id": {"type": "string"},
                "order_category": {"type": "string"},
                "status": {"type": "string"},
                "subscriptions": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["order_id", "subscriptions"],
        },
    },
    {
        "name": "FetchMissingData",
        "description": "Retrieves a single missing field's value from the correct backend system. "
                        "Call once per missing field.",
        "lambda_construct_id": "FetchMissingDataTool",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "subscription_id": {"type": "string"},
                "field": {"type": "string"},
                "fetch_from": {"type": "string"},
                "lookup_key": {"type": "string"},
                "retry_attempt": {"type": "integer"},
            },
            "required": ["order_id", "subscription_id", "field", "fetch_from", "lookup_key"],
        },
    },
    {
        "name": "CheckVASEligibility",
        "description": "Determines if a VAS/device failure is fixable, or a hard business-rule block "
                        "requiring escalation. Call BEFORE FetchMissingData for VAS/Device items.",
        "lambda_construct_id": "CheckVASEligibilityTool",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "subscription_id": {"type": "string"},
                "subscription_type": {"type": "string"},
                "request": {"type": "object"},
            },
            "required": ["order_id", "subscription_id", "subscription_type"],
        },
    },
    {
        "name": "ReprocessOrder",
        "description": "Resubmits a corrected subscription item for activation. Only call after all "
                        "missing fields are fetched. Field values MUST come from a prior "
                        "FetchMissingData result — never fabricate a value.",
        "lambda_construct_id": "ReprocessOrderTool",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "subscription_id": {"type": "string"},
                "subscription_type": {"type": "string"},
                "updated_fields": {"type": "object"},
                "request": {"type": "object"},
            },
            "required": ["order_id", "subscription_id", "subscription_type"],
        },
    },
    {
        "name": "EscalateToHuman",
        "description": "Creates a human-actionable ticket when an issue cannot be auto-resolved. "
                        "Call this when CheckVASEligibility reports not-fixable, or when "
                        "FetchMissingData/ReprocessOrder fail after a retry.",
        "lambda_construct_id": "EscalateToHumanTool",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "subscription_id": {"type": "string"},
                "order_snapshot": {"type": "object"},
                "failure_reason": {"type": "string"},
                "agent_reasoning": {"type": "string"},
                "recommended_action": {"type": "string"},
                "attempted_fixes": {"type": "array", "items": {"type": "string"}},
                "downstream_error": {"type": "object"},
            },
            "required": ["order_id", "subscription_id", "failure_reason", "agent_reasoning"],
        },
    },
]

GATEWAY_CONFIG = {
    "gateway_name": "ora-agent-gateway",
    "tools": TOOL_DEFINITIONS,
}
