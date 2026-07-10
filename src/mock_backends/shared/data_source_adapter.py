"""
Data-source adapter contract — shared interface for mock backends that are
pure lookup sources (not full partner APIs): eSIM Provisioning, Product Catalog,
SIM Inventory, Number Portability, IMEI Registry, Device Inventory/Stock,
Billing Profile.

Simpler than PartnerAdapter (partner_adapter.py) since these backends only
resolve a single field's value, not a full provisioning lifecycle.
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class LookupResponse(TypedDict):
    success: bool
    key: str
    value: Any | None
    error_type: str | None  # e.g. "BACKEND_ERROR", "NOT_FOUND"
    message: str


class DataSourceAdapter(Protocol):
    def lookup(self, key: str) -> LookupResponse:
        """Resolve a single field's value (activation_code, plan_id, iccid, msisdn,
        imei validation result, stock_status, billing_profile_id, etc.) by key."""
        ...
