"""Unit tests for order status derivation (BR-3) — pure logic, no DynamoDB needed."""

from __future__ import annotations

import pytest

from mock_backends.repository.order_status_service import derive_order_status
from mock_backends.shared.domain_models import (
    Order,
    OrderCategory,
    OrderStatus,
    Subscription,
    SubscriptionCategory,
    SubscriptionStatus,
)


def _sub(status: SubscriptionStatus, sub_id: str = "SUB-1") -> Subscription:
    return Subscription(
        order_id="ORD-1", subscription_id=sub_id,
        subscription_category=SubscriptionCategory.CORE_TELCO,
        subscription_type="Mobile Line", provider="eSIM Provisioning",
        status=status,
    )


def test_no_subscriptions_is_pending():
    assert derive_order_status([]) == OrderStatus.PENDING


def test_all_activated_is_activated():
    subs = [_sub(SubscriptionStatus.ACTIVATED, "S1"), _sub(SubscriptionStatus.ACTIVATED, "S2")]
    assert derive_order_status(subs) == OrderStatus.ACTIVATED


def test_all_failed_is_failed():
    subs = [_sub(SubscriptionStatus.FAILED, "S1"), _sub(SubscriptionStatus.FAILED, "S2")]
    assert derive_order_status(subs) == OrderStatus.FAILED


def test_mix_activated_and_failed_is_partially_activated():
    subs = [_sub(SubscriptionStatus.ACTIVATED, "S1"), _sub(SubscriptionStatus.FAILED, "S2")]
    assert derive_order_status(subs) == OrderStatus.PARTIALLY_ACTIVATED


def test_mix_activated_and_pending_is_partially_activated():
    subs = [_sub(SubscriptionStatus.ACTIVATED, "S1"), _sub(SubscriptionStatus.PENDING, "S2")]
    assert derive_order_status(subs) == OrderStatus.PARTIALLY_ACTIVATED


def test_superseded_items_excluded_from_derivation():
    """A SUPERSEDED item (from an Upgrade) should not affect the derived status
    of the currently-active subscriptions."""
    subs = [
        _sub(SubscriptionStatus.SUPERSEDED, "OLD-DEVICE"),
        _sub(SubscriptionStatus.ACTIVATED, "NEW-DEVICE"),
    ]
    assert derive_order_status(subs) == OrderStatus.ACTIVATED


def test_only_superseded_items_is_pending():
    subs = [_sub(SubscriptionStatus.SUPERSEDED, "OLD-DEVICE")]
    assert derive_order_status(subs) == OrderStatus.PENDING


def test_all_pending_is_pending():
    subs = [_sub(SubscriptionStatus.PENDING, "S1")]
    assert derive_order_status(subs) == OrderStatus.PENDING
