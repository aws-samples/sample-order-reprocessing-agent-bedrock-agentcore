"""
Repository layer for CRMOrders — boto3-based DynamoDB access.

Per component-methods.md, business-rules.md (BR-1 through BR-3), and
domain-entities.md.
"""

from __future__ import annotations

from typing import Optional

import boto3
from botocore.exceptions import ClientError

from mock_backends.repository.config import AWS_REGION, CRM_ORDERS_TABLE
from mock_backends.shared.domain_models import Order, OrderStatus


def _table():
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return dynamodb.Table(CRM_ORDERS_TABLE)


def create_order(order: Order) -> None:
    """BR-1: every order placement creates a new CRMOrders record."""
    _table().put_item(Item=order.to_item())


def get_order(order_id: str) -> Optional[Order]:
    response = _table().get_item(Key={"order_id": order_id})
    item = response.get("Item")
    return Order.from_item(item) if item else None


def update_order_status(order_id: str, new_status: OrderStatus, updated_at: str) -> bool:
    """Update the parent order's status. Unlike subscription-level updates,
    order status is a derived value (BR-3) recomputed by the caller — this
    repository function just persists whatever value it's given.

    Returns True if the update succeeded, False if the order didn't exist.
    """
    try:
        _table().update_item(
            Key={"order_id": order_id},
            UpdateExpression="SET #status = :status, updated_at = :updated_at",
            ConditionExpression="attribute_exists(order_id)",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": new_status.value, ":updated_at": updated_at},
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def query_orders_by_status(status: OrderStatus) -> list[Order]:
    """Uses the status-updated_at-index GSI (per domain-entities.md) to support
    the Issues tab query ('all ESCALATED or PARTIALLY_ACTIVATED orders')."""
    response = _table().query(
        IndexName="status-updated_at-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("status").eq(status.value),
    )
    return [Order.from_item(item) for item in response.get("Items", [])]


def scan_all_orders() -> list[Order]:
    """Used by the Order Summary tab (Unit 4) for the full order list.
    A scan is acceptable at this scale (samples/workshop, hundreds of orders,
    not production-scale) — see nfr-requirements.md (no specific latency SLA)."""
    response = _table().scan()
    return [Order.from_item(item) for item in response.get("Items", [])]
