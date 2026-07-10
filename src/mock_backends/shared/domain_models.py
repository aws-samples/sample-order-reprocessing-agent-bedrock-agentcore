"""
Domain model shared types for the Order Reprocessing Agent.

Defines the core data structures used across the Mock Backend Data Layer (Unit 1)
and consumed by Agent Tools (Unit 2), Order Placement Service (Unit 3), and the
Operator UI (Unit 4).

See: aidlc-docs/inception/application-design/domain-entities.md (via
     aidlc-docs/construction/mock-backend-data-layer/functional-design/domain-entities.md)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FAILED = "FAILED"
    PARTIALLY_ACTIVATED = "PARTIALLY_ACTIVATED"
    ACTIVATED = "ACTIVATED"
    ESCALATED = "ESCALATED"


class SubscriptionStatus(str, Enum):
    PENDING = "PENDING"
    FAILED = "FAILED"
    ACTIVATED = "ACTIVATED"
    SUPERSEDED = "SUPERSEDED"


class SubscriptionCategory(str, Enum):
    CORE_TELCO = "Core Telco"
    VALUE_ADDED_SERVICE = "Value-Added Service"


class OrderCategory(str, Enum):
    NEW_CONNECTION = "New Connection"
    UPGRADE = "Upgrade"
    ADD_SUBSCRIPTION = "Add Subscription"


class DeviceCategory(str, Enum):
    STANDARD = "Standard"
    FOLDABLE = "Foldable"
    FLAGSHIP = "Flagship"


class FinancingType(str, Enum):
    FULL_PAYMENT = "Full Payment"
    INSTALLMENT_12MO = "Installment-12mo"
    INSTALLMENT_24MO = "Installment-24mo"
    TRADE_IN_INSTALLMENT = "Trade-in + Installment"


class StockStatus(str, Enum):
    IN_STOCK = "In Stock"
    BACKORDER = "Backorder"
    PRE_ORDER = "Pre-order"


class HistoryEventType(str, Enum):
    DETECTED = "DETECTED"
    VALIDATED = "VALIDATED"
    FETCHED_DATA = "FETCHED_DATA"
    REPROCESSED = "REPROCESSED"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    BACKEND_ERROR = "BACKEND_ERROR"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Subscription:
    """A single subscription item within an order (CRMOrderSubscriptions record)."""

    order_id: str
    subscription_id: str
    subscription_category: SubscriptionCategory
    subscription_type: str  # e.g. "Mobile Line", "Device Purchase/Financing", "Netflix"
    provider: str  # which mock backend adapter owns this item's data
    status: SubscriptionStatus = SubscriptionStatus.PENDING
    failure_reason: Optional[str] = None
    depends_on: Optional[str] = None  # single subscription_id (per Q1: A)

    # Core Telco fields
    msisdn: Optional[str] = None
    sim_type: Optional[str] = None
    activation_code: Optional[str] = None
    iccid: Optional[str] = None
    plan_id: Optional[str] = None

    # Device fields
    device_model: Optional[str] = None
    device_category: Optional[DeviceCategory] = None
    financing_type: Optional[FinancingType] = None
    imei: Optional[str] = None
    stock_status: Optional[StockStatus] = None
    esim_compatible: Optional[bool] = None

    # VAS fields
    vas_account_ref: Optional[str] = None
    vas_entitlement_status: Optional[str] = None

    def to_item(self) -> dict[str, Any]:
        """Serialize to a DynamoDB-item-compatible dict, dropping None values."""
        item = {
            "order_id": self.order_id,
            "subscription_id": self.subscription_id,
            "subscription_category": self.subscription_category.value,
            "subscription_type": self.subscription_type,
            "provider": self.provider,
            "status": self.status.value,
        }
        optional_fields = {
            "failure_reason": self.failure_reason,
            "depends_on": self.depends_on,
            "msisdn": self.msisdn,
            "sim_type": self.sim_type,
            "activation_code": self.activation_code,
            "iccid": self.iccid,
            "plan_id": self.plan_id,
            "device_model": self.device_model,
            "device_category": self.device_category.value if self.device_category else None,
            "financing_type": self.financing_type.value if self.financing_type else None,
            "imei": self.imei,
            "stock_status": self.stock_status.value if self.stock_status else None,
            "esim_compatible": self.esim_compatible,
            "vas_account_ref": self.vas_account_ref,
            "vas_entitlement_status": self.vas_entitlement_status,
        }
        for key, value in optional_fields.items():
            if value is not None:
                item[key] = value
        return item

    @staticmethod
    def from_item(item: dict[str, Any]) -> "Subscription":
        return Subscription(
            order_id=item["order_id"],
            subscription_id=item["subscription_id"],
            subscription_category=SubscriptionCategory(item["subscription_category"]),
            subscription_type=item["subscription_type"],
            provider=item["provider"],
            status=SubscriptionStatus(item.get("status", SubscriptionStatus.PENDING.value)),
            failure_reason=item.get("failure_reason"),
            depends_on=item.get("depends_on"),
            msisdn=item.get("msisdn"),
            sim_type=item.get("sim_type"),
            activation_code=item.get("activation_code"),
            iccid=item.get("iccid"),
            plan_id=item.get("plan_id"),
            device_model=item.get("device_model"),
            device_category=DeviceCategory(item["device_category"]) if item.get("device_category") else None,
            financing_type=FinancingType(item["financing_type"]) if item.get("financing_type") else None,
            imei=item.get("imei"),
            stock_status=StockStatus(item["stock_status"]) if item.get("stock_status") else None,
            esim_compatible=item.get("esim_compatible"),
            vas_account_ref=item.get("vas_account_ref"),
            vas_entitlement_status=item.get("vas_entitlement_status"),
        )


@dataclass
class Order:
    """A parent order record (CRMOrders record) with its subscription items."""

    order_id: str
    customer_id: str
    order_category: OrderCategory
    status: OrderStatus = OrderStatus.PENDING
    subscriptions: list[Subscription] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    @property
    def subscription_count(self) -> int:
        return len(self.subscriptions)

    def to_item(self) -> dict[str, Any]:
        """Serialize the parent order record only (subscriptions stored separately)."""
        return {
            "order_id": self.order_id,
            "customer_id": self.customer_id,
            "order_category": self.order_category.value,
            "status": self.status.value,
            "subscription_count": self.subscription_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_item(item: dict[str, Any]) -> "Order":
        return Order(
            order_id=item["order_id"],
            customer_id=item["customer_id"],
            order_category=OrderCategory(item["order_category"]),
            status=OrderStatus(item.get("status", OrderStatus.PENDING.value)),
            created_at=item.get("created_at", _now_iso()),
            updated_at=item.get("updated_at", _now_iso()),
        )


@dataclass
class HistoryEvent:
    """An immutable, append-only record in OrderProcessingHistory."""

    order_id: str
    event_type: HistoryEventType
    tool_name: str
    summary: str
    resulting_status: str
    subscription_id: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    event_timestamp: str = field(default_factory=_now_iso)

    def to_item(self) -> dict[str, Any]:
        item = {
            "order_id": self.order_id,
            "event_timestamp": self.event_timestamp,
            "event_type": self.event_type.value,
            "tool_name": self.tool_name,
            "summary": self.summary,
            "resulting_status": self.resulting_status,
            "details": self.details,
        }
        if self.subscription_id is not None:
            item["subscription_id"] = self.subscription_id
        return item

    @staticmethod
    def from_item(item: dict[str, Any]) -> "HistoryEvent":
        return HistoryEvent(
            order_id=item["order_id"],
            event_timestamp=item["event_timestamp"],
            event_type=HistoryEventType(item["event_type"]),
            tool_name=item["tool_name"],
            summary=item["summary"],
            resulting_status=item["resulting_status"],
            details=item.get("details", {}),
            subscription_id=item.get("subscription_id"),
        )
