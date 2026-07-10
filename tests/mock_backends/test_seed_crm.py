"""Verification test for seed_crm.py — confirms it runs against mocked DynamoDB
and produces a representative status mix (BR-13), not all PENDING."""

from __future__ import annotations

from collections import Counter


def test_seed_script_creates_100_orders_with_status_variety(dynamodb_tables):
    from mock_backends.repository import orders_repository
    from mock_backends.seed.seed_crm import seed

    seed()

    all_orders = orders_repository.scan_all_orders()
    assert len(all_orders) == 100

    status_counts = Counter(o.status for o in all_orders)
    # BR-13: must include a representative mix, not all one status.
    assert len(status_counts) >= 3, f"Expected status variety, got: {status_counts}"


def test_seed_script_creates_subscriptions_for_orders(dynamodb_tables):
    from mock_backends.repository import orders_repository, subscriptions_repository
    from mock_backends.seed.seed_crm import seed

    seed()

    all_orders = orders_repository.scan_all_orders()
    sample_order = all_orders[0]
    subs = subscriptions_repository.query_subscriptions_for_order(sample_order.order_id)
    assert len(subs) >= 1  # at minimum, a mobile line subscription
