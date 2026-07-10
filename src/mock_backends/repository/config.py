"""
Repository configuration — DynamoDB table names, matching infrastructure-design.md
and logical-components.md naming (`ora-` prefix, per NFR-5).
"""

from __future__ import annotations

import os

CRM_ORDERS_TABLE = os.environ.get("CRM_ORDERS_TABLE", "ora-crm-orders")
CRM_ORDER_SUBSCRIPTIONS_TABLE = os.environ.get("CRM_ORDER_SUBSCRIPTIONS_TABLE", "ora-crm-order-subscriptions")
ORDER_PROCESSING_HISTORY_TABLE = os.environ.get("ORDER_PROCESSING_HISTORY_TABLE", "ora-order-processing-history")
DEVICE_INVENTORY_TABLE = os.environ.get("DEVICE_INVENTORY_TABLE", "ora-device-inventory")

AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")
