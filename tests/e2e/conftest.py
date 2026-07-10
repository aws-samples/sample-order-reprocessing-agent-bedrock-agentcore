"""
E2E test fixtures — Unit 6.

Unlike Units 1-4's conftest.py (moto-mocked DynamoDB), these fixtures use REAL
boto3 clients against a REAL deployed AWS stack. Requires Unit 5's
`infrastructure/app.py` to have been deployed with `-c operatingMode=DEMO`
BEFORE running any test in this directory.

Resource names are read from environment variables with defaults matching
Unit 3/1's CDK constructs' hardcoded `function_name`/`table_name` values
(order_placement_service.py, mock_backend_data_layer.py) — these are stable
across deployments since they aren't CDK-auto-generated names.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import boto3
import pytest

REGION = os.environ.get("ORA_E2E_REGION", "eu-west-2")
ORDER_PLACEMENT_FUNCTION = os.environ.get("ORA_ORDER_PLACEMENT_FUNCTION", "ora-order-placement-service")
CRM_ORDERS_TABLE = os.environ.get("ORA_CRM_ORDERS_TABLE", "ora-crm-orders")
CRM_ORDER_SUBSCRIPTIONS_TABLE = os.environ.get("ORA_CRM_ORDER_SUBSCRIPTIONS_TABLE", "ora-crm-order-subscriptions")
ORDER_PROCESSING_HISTORY_TABLE = os.environ.get("ORA_ORDER_PROCESSING_HISTORY_TABLE", "ora-order-processing-history")

# Terminal statuses per FR-3/domain_models.OrderStatus — polling stops here.
_TERMINAL_ORDER_STATUSES = {"ACTIVATED", "PARTIALLY_ACTIVATED", "ESCALATED"}

# Default poll timeout. The agent invocation chain (EventBridge -> Runtime
# Invoker Lambda -> AgentCore Runtime -> tool calls) is async from
# place_order()'s perspective, so tests must poll rather than assume
# synchronous completion.
DEFAULT_POLL_TIMEOUT_SECONDS = 60
DEFAULT_POLL_INTERVAL_SECONDS = 3


@pytest.fixture(scope="session")
def lambda_client():
    return boto3.client("lambda", region_name=REGION)


@pytest.fixture(scope="session")
def dynamodb_resource():
    return boto3.resource("dynamodb", region_name=REGION)


@pytest.fixture(scope="session")
def crm_orders_table(dynamodb_resource):
    return dynamodb_resource.Table(CRM_ORDERS_TABLE)


@pytest.fixture(scope="session")
def crm_order_subscriptions_table(dynamodb_resource):
    return dynamodb_resource.Table(CRM_ORDER_SUBSCRIPTIONS_TABLE)


@pytest.fixture(scope="session")
def order_processing_history_table(dynamodb_resource):
    return dynamodb_resource.Table(ORDER_PROCESSING_HISTORY_TABLE)


@dataclass
class PlacedOrder:
    order_id: str
    subscription_ids: list[str]
    initial_outcome: str
    failure_subscription_id: Optional[str]
    scenario: Optional[str]


def place_demo_order(
    lambda_client,
    *,
    customer_id: str,
    order_category: str = "New Connection",
    plan_id: str = "PLAN-STANDARD-5G",
    device_selection: Optional[dict[str, Any]] = None,
    vas_selections: Optional[list[str]] = None,
    forced_scenario: Optional[str] = None,
    forced_subscription_type: Optional[str] = None,
) -> PlacedOrder:
    """Invokes the REAL ora-order-placement-service Lambda. Matches
    service.py's handler() event shape exactly (customer_id, order_category,
    plan_id, device_selection, vas_selections, demo_mode_override)."""
    payload: dict[str, Any] = {
        "customer_id": customer_id,
        "order_category": order_category,
        "plan_id": plan_id,
        "vas_selections": vas_selections or [],
    }
    if device_selection is not None:
        payload["device_selection"] = device_selection
    if forced_scenario is not None:
        payload["demo_mode_override"] = {
            "forced_scenario": forced_scenario,
            "forced_subscription_type": forced_subscription_type,
        }

    response = lambda_client.invoke(
        FunctionName=ORDER_PLACEMENT_FUNCTION,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    result = json.loads(response["Payload"].read())
    if "errorMessage" in result:
        raise RuntimeError(f"place_demo_order Lambda invocation failed: {result}")

    return PlacedOrder(
        order_id=result["order_id"],
        subscription_ids=result["subscription_ids"],
        initial_outcome=result["initial_outcome"],
        failure_subscription_id=result.get("failure_subscription_id"),
        scenario=result.get("scenario"),
    )


def poll_until_terminal(
    crm_orders_table,
    order_id: str,
    *,
    timeout_seconds: int = DEFAULT_POLL_TIMEOUT_SECONDS,
    interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Polls the REAL ora-crm-orders table until the order reaches a terminal
    status (ACTIVATED/PARTIALLY_ACTIVATED/ESCALATED) or times out.

    Raises TimeoutError on timeout, distinct from Unit 4's
    trigger_logic.poll_for_terminal_status() (UI-facing, 30s max per BR-39) —
    this one is test-assertion-facing and allows a longer window since it must
    account for the full async agent invocation chain, not just user-visible
    responsiveness."""
    deadline = time.monotonic() + timeout_seconds
    last_item: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = crm_orders_table.get_item(Key={"order_id": order_id})
        item = response.get("Item")
        if item is not None:
            last_item = item
            if item.get("status") in _TERMINAL_ORDER_STATUSES:
                return item
        time.sleep(interval_seconds)

    raise TimeoutError(
        f"Order {order_id} did not reach a terminal status within {timeout_seconds}s. "
        f"Last known state: {last_item}"
    )


def get_subscription(crm_order_subscriptions_table, order_id: str, subscription_id: str) -> dict[str, Any]:
    response = crm_order_subscriptions_table.get_item(
        Key={"order_id": order_id, "subscription_id": subscription_id}
    )
    item = response.get("Item")
    if item is None:
        raise AssertionError(f"Subscription {subscription_id} not found for order {order_id}")
    return item


def get_history_events(order_processing_history_table, order_id: str) -> list[dict[str, Any]]:
    response = order_processing_history_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("order_id").eq(order_id)
    )
    return sorted(response.get("Items", []), key=lambda e: e["event_timestamp"])
