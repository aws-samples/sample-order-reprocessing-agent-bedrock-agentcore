"""
Failure Injection Engine — determines whether and how a placed order encounters
a failure, in either Realistic Mode (probabilistic) or Demo Mode (deterministic).

Per component-methods.md (2.13), business-rules.md (BR-6 through BR-9), and
business-logic-model.md (Failure Injection Algorithm).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from mock_backends.shared.domain_models import (
    DeviceCategory,
    FinancingType,
    Order,
    Subscription,
    SubscriptionCategory,
)

_CONFIG_CACHE: Optional[dict[str, Any]] = None


def load_failure_probability_config(config_path: Optional[Path] = None) -> dict[str, Any]:
    """Load (and cache) the FailureProbabilityConfig JSON. Cached at module level
    to mimic Lambda cold-start-once behavior.

    Uses JSON, not YAML, specifically so no third-party pyyaml dependency is
    needed at Lambda runtime — Code.from_asset() (used throughout this
    project's CDK constructs) does not pip-install dependencies into the
    deployed zip, only boto3 is preinstalled in the Lambda runtime image.
    This was a REAL bug found during the first live deployment: the original
    YAML-based config caused a Runtime.ImportModuleError ("No module named
    'yaml'") the first time the real order placement Lambda was invoked
    against a genuine AWS account — not catchable via local moto-based tests,
    since those run in a full dev venv with pyyaml installed."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    if config_path is None:
        config_path = Path(__file__).parent / "failure_probabilities.json"

    with open(config_path, "r", encoding="utf-8") as f:
        _CONFIG_CACHE = json.load(f)
    return _CONFIG_CACHE


@dataclass
class OutcomeDecision:
    will_fail: bool
    failure_subscription_id: Optional[str] = None
    scenario: Optional[str] = None
    is_non_fetchable: bool = False


def _compute_failure_weight(order: Order, subscription: Subscription, config: dict[str, Any]) -> float:
    """BR-6: weight = base_failure_rate * device_category_weight * vas_type_weight * order_category_weight"""
    weight = config["base_failure_rate"]

    if subscription.device_category is not None:
        weight *= config["weights"]["device_category"].get(subscription.device_category.value, 1.0)

    if subscription.subscription_category == SubscriptionCategory.VALUE_ADDED_SERVICE:
        weight *= config["weights"]["vas_type"].get(subscription.subscription_type, 1.0)

    weight *= config["weights"]["order_category"].get(order.order_category.value, 1.0)

    return weight


def _select_scenario(subscription: Subscription, config: dict[str, Any]) -> str:
    """business-logic-model.md step 2a: pick a scenario from the pool matching
    the subscription's category, respecting applicability constraints."""
    pools = config["scenario_pools"]

    if subscription.subscription_category == SubscriptionCategory.VALUE_ADDED_SERVICE:
        return random.choice(pools["vas"])  # nosec B311 -- simulated failure scenario selection, not crypto

    if subscription.subscription_type == "Device Purchase/Financing":
        candidates = list(pools["device"])
        if subscription.device_category != DeviceCategory.FOLDABLE:
            candidates = [c for c in candidates if c != "foldable_esim_quirk"]
        if subscription.financing_type != FinancingType.TRADE_IN_INSTALLMENT:
            candidates = [c for c in candidates if c != "trade_in_valuation_mismatch"]
        return random.choice(candidates)  # nosec B311 -- simulated failure scenario selection, not crypto

    return random.choice(pools["core_telco"])  # nosec B311 -- simulated failure scenario selection, not crypto


def determine_outcome(
    order: Order,
    mode: str,  # "REALISTIC" | "DEMO"
    forced_scenario: Optional[str] = None,
    forced_subscription_id: Optional[str] = None,
    config: Optional[dict[str, Any]] = None,
) -> OutcomeDecision:
    """
    Determine whether an order encounters a failure, per BR-6/BR-7.

    Realistic Mode: probabilistic, weighted by order contents.
    Demo Mode: deterministic, explicit scenario forced onto a target subscription.
    """
    if config is None:
        config = load_failure_probability_config()

    if mode == "DEMO":
        if forced_scenario is None or forced_subscription_id is None:
            raise ValueError("Demo Mode requires forced_scenario and forced_subscription_id")
        is_non_fetchable = forced_scenario in config["non_fetchable_scenarios"]
        return OutcomeDecision(
            will_fail=True,
            failure_subscription_id=forced_subscription_id,
            scenario=forced_scenario,
            is_non_fetchable=is_non_fetchable,
        )

    if mode != "REALISTIC":
        raise ValueError(f"Unknown mode: {mode!r}, expected 'REALISTIC' or 'DEMO'")

    for subscription in order.subscriptions:
        weight = _compute_failure_weight(order, subscription, config)
        roll = random.random()  # nosec B311 -- simulated failure probability roll, not crypto
        if roll < weight:
            scenario = _select_scenario(subscription, config)
            is_non_fetchable = scenario in config["non_fetchable_scenarios"]
            return OutcomeDecision(
                will_fail=True,
                failure_subscription_id=subscription.subscription_id,
                scenario=scenario,
                is_non_fetchable=is_non_fetchable,
            )

    return OutcomeDecision(will_fail=False)
