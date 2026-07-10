"""Shared pytest fixtures for repository-layer tests: moto-mocked DynamoDB
tables matching infrastructure-design.md's table definitions."""

from __future__ import annotations

import os

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def aws_credentials():
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"  # nosec B105 -- moto fake credential fixture, not a real secret
    os.environ["AWS_SECURITY_TOKEN"] = "testing"  # nosec B105 -- moto fake credential fixture, not a real secret
    os.environ["AWS_SESSION_TOKEN"] = "testing"  # nosec B105 -- moto fake credential fixture, not a real secret
    os.environ["AWS_REGION"] = "eu-west-2"


@pytest.fixture
def dynamodb_tables(aws_credentials):
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

        dynamodb.create_table(
            TableName="ora-order-processing-history",
            KeySchema=[
                {"AttributeName": "order_id", "KeyType": "HASH"},
                {"AttributeName": "event_timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "order_id", "AttributeType": "S"},
                {"AttributeName": "event_timestamp", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        dynamodb.create_table(
            TableName="ora-device-inventory",
            KeySchema=[{"AttributeName": "device_model", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "device_model", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        yield dynamodb
