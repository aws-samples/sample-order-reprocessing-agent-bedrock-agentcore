"""
AWS client helpers — boto3 client factory using the default credential chain
(Q2: A), consistent with NFR-11's "runs locally, assumes already-configured
AWS credentials" design.
"""

from __future__ import annotations

import os
from functools import lru_cache

import boto3

_REGION = os.environ.get("AWS_REGION", "eu-west-2")


@lru_cache(maxsize=None)
def get_dynamodb_resource():
    return boto3.resource("dynamodb", region_name=_REGION)


@lru_cache(maxsize=None)
def get_lambda_client():
    return boto3.client("lambda", region_name=_REGION)


@lru_cache(maxsize=None)
def get_logs_client():
    return boto3.client("logs", region_name=_REGION)
