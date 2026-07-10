"""Unit tests for order_placement_service.ambient_activity."""

from __future__ import annotations

import pytest

from order_placement_service.ambient_activity import _generate_random_request, generate_ambient_activity


@pytest.fixture(autouse=True)
def _realistic_mode(monkeypatch):
    monkeypatch.setenv("OPERATING_MODE", "REALISTIC")


def test_generate_random_request_produces_valid_category():
    for _ in range(20):
        request = _generate_random_request()
        assert request.order_category in ("New Connection", "Upgrade", "Add Subscription")
        assert request.customer_id.startswith("CUST-AMBIENT-")


def test_generate_random_request_add_subscription_has_no_device():
    found_add_subscription = False
    for _ in range(50):
        request = _generate_random_request()
        if request.order_category == "Add Subscription":
            found_add_subscription = True
            assert request.device_selection is None
    assert found_add_subscription, "Expected at least one Add Subscription in 50 random samples"


def test_generate_random_request_new_connection_has_device():
    found_new_connection = False
    for _ in range(50):
        request = _generate_random_request()
        if request.order_category == "New Connection":
            found_new_connection = True
            assert request.device_selection is not None
    assert found_new_connection, "Expected at least one New Connection in 50 random samples"


def test_generate_ambient_activity_calls_place_order_end_to_end(dynamodb_tables):
    result = generate_ambient_activity()
    assert result["order_id"].startswith("ORD-")
    assert result["customer_id"].startswith("CUST-AMBIENT-")
    assert result["initial_outcome"] in ("WILL_SUCCEED", "WILL_FAIL")
