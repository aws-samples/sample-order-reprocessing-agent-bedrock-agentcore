"""
Mock Device Inventory/Stock Adapter — tracks stock_status for specific handset
SKUs. Implements DataSourceAdapter contract.

Per components.md (2.7), business-rules.md (BR-8: static per device_model,
shared inventory), infrastructure-design.md (Lambda: ora-adapter-device-inventory).

UPDATED (post-Unit-1-review): now backed by the real `ora-device-inventory`
DynamoDB table via device_inventory_repository.py, instead of an in-memory
dict — ensuring BR-8's "all orders see the same current stock state" holds
true across separate Lambda invocations/cold starts, not just within a
single process.
"""

from __future__ import annotations

from typing import Any

from mock_backends.repository import device_inventory_repository
from mock_backends.shared.data_source_adapter import LookupResponse
from mock_backends.shared.domain_models import StockStatus


def lookup(key: str) -> LookupResponse:
    """key = device_model. Returns the current shared stock_status for that model,
    persisted in DynamoDB (BR-8)."""
    if not key:
        return LookupResponse(
            success=False, key=key, value=None,
            error_type="NOT_FOUND", message="device_model is required to check stock status",
        )

    status = device_inventory_repository.get_stock_status(key)

    return LookupResponse(
        success=True, key=key, value=status.value, error_type=None,
        message=f"stock_status resolved from Device Inventory/Stock system for {key}",
    )


def set_stock_status(device_model: str, status: StockStatus) -> None:
    """Test/Demo-Mode helper to control a device model's shared stock state."""
    device_inventory_repository.set_stock_status(device_model, status)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    result = lookup(event.get("key", ""))
    return dict(result)
