"""Shared pytest fixtures for order_placement_service tests — same moto-mocked
DynamoDB tables pattern as mock_backends/agent tests."""

from __future__ import annotations

import os

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def aws_credentials():
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_REGION"] = "eu-west-2"


@pytest.fixture
def dynamodb_tables(aws_credentials):
    """Single unified mock_aws context covering both DynamoDB and EventBridge,
    since place_order() uses both within one call (creates records, then
    fires an event) — two separate mock_aws() contexts would not share state."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="eu-west-2")

        dynamodb.create_table(
            TableName="ora-crm-orders",
            KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "order_id", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "updated_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "status-updated_at-index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "updated_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        dynamodb.create_table(
            TableName="ora-crm-order-subscriptions",
            KeySchema=[
                {"AttributeName": "order_id", "KeyType": "HASH"},
                {"AttributeName": "subscription_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "order_id", "AttributeType": "S"},
                {"AttributeName": "subscription_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # EventBridge default event bus exists automatically under mock_aws();
        # no explicit bus creation needed for put_events to work against "default".
        yield dynamodb
