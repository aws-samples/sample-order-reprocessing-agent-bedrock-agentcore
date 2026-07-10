"""
Repository layer for CRMOrderSubscriptions — boto3-based DynamoDB access.

Implements idempotent status transitions per BR-12: a write to set
status=ACTIVATED must assert the current status is FAILED or PENDING
(not already ACTIVATED), preventing duplicate reprocessing from being
applied twice on agent/Lambda/EventBridge retries.
"""

from __future__ import annotations

from typing import Optional

import boto3
from botocore.exceptions import ClientError

from mock_backends.repository.config import AWS_REGION, CRM_ORDER_SUBSCRIPTIONS_TABLE
from mock_backends.shared.domain_models import Subscription, SubscriptionStatus


def _table():
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return dynamodb.Table(CRM_ORDER_SUBSCRIPTIONS_TABLE)


def create_subscription(subscription: Subscription) -> None:
    _table().put_item(Item=subscription.to_item())


def get_subscription(order_id: str, subscription_id: str) -> Optional[Subscription]:
    response = _table().get_item(Key={"order_id": order_id, "subscription_id": subscription_id})
    item = response.get("Item")
    return Subscription.from_item(item) if item else None


def query_subscriptions_for_order(order_id: str) -> list[Subscription]:
    response = _table().query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("order_id").eq(order_id),
    )
    return [Subscription.from_item(item) for item in response.get("Items", [])]


def update_subscription_fields(order_id: str, subscription_id: str, fields: dict) -> None:
    """Used by FetchMissingData/ReprocessOrder (Unit 2) to persist newly-fetched
    field values (e.g., a resolved activation_code) before/while reprocessing."""
    if not fields:
        return
    update_expr_parts = []
    expr_values = {}
    expr_names = {}
    for i, (key, value) in enumerate(fields.items()):
        placeholder = f":v{i}"
        name_placeholder = f"#f{i}"
        update_expr_parts.append(f"{name_placeholder} = {placeholder}")
        expr_values[placeholder] = value
        expr_names[name_placeholder] = key

    _table().update_item(
        Key={"order_id": order_id, "subscription_id": subscription_id},
        UpdateExpression="SET " + ", ".join(update_expr_parts),
        ExpressionAttributeValues=expr_values,
        ExpressionAttributeNames=expr_names,
    )


def transition_status_idempotent(
    order_id: str,
    subscription_id: str,
    new_status: SubscriptionStatus,
    allowed_current_statuses: list[SubscriptionStatus],
) -> bool:
    """BR-12: conditional write guarding against duplicate reprocessing.

    Returns True if the transition was applied, False if it was skipped
    because the subscription was already in a state not in
    `allowed_current_statuses` (i.e., this exact transition was already
    applied by a prior attempt — the idempotent no-op case).
    """
    condition_values = {f":s{i}": s.value for i, s in enumerate(allowed_current_statuses)}
    condition_expr = "#status IN (" + ", ".join(condition_values.keys()) + ")"

    try:
        _table().update_item(
            Key={"order_id": order_id, "subscription_id": subscription_id},
            UpdateExpression="SET #status = :new_status",
            ConditionExpression=condition_expr,
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={**condition_values, ":new_status": new_status.value},
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def mark_superseded(order_id: str, subscription_id: str) -> bool:
    """BR-2/BR-28: mark a prior device subscription as SUPERSEDED during an
    Upgrade order. SUPERSEDED items remain permanently in this table (per Q2: A)."""
    return transition_status_idempotent(
        order_id,
        subscription_id,
        new_status=SubscriptionStatus.SUPERSEDED,
        allowed_current_statuses=[SubscriptionStatus.ACTIVATED],
    )
