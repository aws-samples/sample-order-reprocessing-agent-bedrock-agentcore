"""
Repository layer for DeviceInventory — the shared, static-per-device_model
stock status table (BR-8). Backs the Device Inventory/Stock Adapter with real
DynamoDB persistence instead of an in-memory dict, so stock state is
consistent across separate Lambda invocations/cold starts.
"""

from __future__ import annotations

from typing import Optional

import boto3

from mock_backends.repository.config import AWS_REGION, DEVICE_INVENTORY_TABLE
from mock_backends.shared.domain_models import StockStatus

# Seed defaults applied on first lookup if the table has no record yet for a
# given device_model (mirrors the original in-memory defaults for continuity).
_DEFAULT_STOCK: dict[str, StockStatus] = {
    "iPhone 16 Pro Max": StockStatus.IN_STOCK,
    "Samsung Galaxy Z Fold 6": StockStatus.BACKORDER,
    "Samsung Galaxy S24": StockStatus.IN_STOCK,
}


def _table():
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return dynamodb.Table(DEVICE_INVENTORY_TABLE)


def get_stock_status(device_model: str) -> StockStatus:
    """BR-8: shared, static-per-device_model lookup. If no record exists yet,
    seeds one from _DEFAULT_STOCK (or PRE_ORDER for unknown models) and persists
    it, so subsequent calls (from any Lambda invocation) see the same value."""
    response = _table().get_item(Key={"device_model": device_model})
    item = response.get("Item")
    if item:
        return StockStatus(item["stock_status"])

    default_status = _DEFAULT_STOCK.get(device_model, StockStatus.PRE_ORDER)
    set_stock_status(device_model, default_status)
    return default_status


def set_stock_status(device_model: str, status: StockStatus) -> None:
    """Persists the shared stock status for a device_model. Used both by the
    lazy-seed path in get_stock_status() and by test/Demo-Mode helpers wanting
    to force a specific stock state."""
    _table().put_item(Item={"device_model": device_model, "stock_status": status.value})
