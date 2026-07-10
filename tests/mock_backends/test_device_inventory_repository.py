"""Unit tests for device_inventory_repository.py — verifies DynamoDB-backed
persistence of shared stock status (BR-8), replacing the earlier in-memory
dict implementation flagged during Unit 1 review."""

from __future__ import annotations

from mock_backends.repository import device_inventory_repository
from mock_backends.shared.domain_models import StockStatus


def test_get_stock_status_seeds_known_default(dynamodb_tables):
    status = device_inventory_repository.get_stock_status("Samsung Galaxy Z Fold 6")
    assert status == StockStatus.BACKORDER


def test_get_stock_status_seeds_pre_order_for_unknown_model(dynamodb_tables):
    status = device_inventory_repository.get_stock_status("Totally Unknown Phone")
    assert status == StockStatus.PRE_ORDER


def test_get_stock_status_persists_across_lookups(dynamodb_tables):
    """Simulates two separate Lambda invocations both calling lookup — both
    must see the same persisted value, not independently-seeded defaults."""
    first = device_inventory_repository.get_stock_status("iPhone 16 Pro Max")
    second = device_inventory_repository.get_stock_status("iPhone 16 Pro Max")
    assert first == second == StockStatus.IN_STOCK


def test_set_stock_status_overrides_default(dynamodb_tables):
    device_inventory_repository.set_stock_status("iPhone 16 Pro Max", StockStatus.BACKORDER)
    status = device_inventory_repository.get_stock_status("iPhone 16 Pro Max")
    assert status == StockStatus.BACKORDER
