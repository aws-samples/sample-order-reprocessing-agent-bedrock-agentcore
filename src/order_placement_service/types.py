"""
Shared types for Unit 3 (Order Placement Service).

Per domain-entities.md: PlaceOrderRequest, PlaceOrderResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DeviceSelection:
    device_model: str
    device_category: str  # "Standard" | "Foldable" | "Flagship"
    financing_type: str
    esim_compatible: bool = True


@dataclass
class DemoModeOverride:
    forced_scenario: str
    forced_subscription_type: str  # which subscription_type/category the scenario applies to


@dataclass
class PlaceOrderRequest:
    customer_id: str
    order_category: str  # "New Connection" | "Upgrade" | "Add Subscription"
    plan_id: str
    device_selection: Optional[DeviceSelection] = None
    vas_selections: list[str] = field(default_factory=list)
    demo_mode_override: Optional[DemoModeOverride] = None


@dataclass
class PlaceOrderResult:
    order_id: str
    subscription_ids: list[str]
    initial_outcome: str  # "WILL_SUCCEED" | "WILL_FAIL"
    event_fired: bool
    failure_subscription_id: Optional[str] = None
    scenario: Optional[str] = None
