"""
Repository layer for OrderProcessingHistory — boto3-based DynamoDB access.

Per BR-11: history records are immutable and append-only — this module only
supports create/query, never update or delete.
"""

from __future__ import annotations

import boto3

from mock_backends.repository.config import AWS_REGION, ORDER_PROCESSING_HISTORY_TABLE
from mock_backends.shared.domain_models import HistoryEvent


def _table():
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return dynamodb.Table(ORDER_PROCESSING_HISTORY_TABLE)


def record_history_event(event: HistoryEvent) -> None:
    """The shared History Recorder utility (used internally by all 6 agent
    tools in Unit 2) calls this to append an immutable event. BR-11: append-only,
    never updated or deleted."""
    _table().put_item(Item=event.to_item())


def query_history_for_order(order_id: str) -> list[HistoryEvent]:
    """Access pattern per Q5: A — query by order_id only, sorted chronologically
    by event_timestamp (the table's sort key), no cross-order GSI in v1."""
    response = _table().query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("order_id").eq(order_id),
        ScanIndexForward=True,  # chronological order
    )
    return [HistoryEvent.from_item(item) for item in response.get("Items", [])]
