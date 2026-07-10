"""
PartnerAdapter contract — shared interface implemented by all mock backend
partner-style adapters (GVPM, Netflix, Spotify, Disney+).

Per Application Design (component-methods.md, Q10: A) and NFR Design
(nfr-design-patterns.md), this is a Python Protocol enforcing a consistent
method contract across partner adapters, so agent tools (Unit 2) can invoke
any adapter generically.

Data-source-only adapters (eSIM Provisioning, Product Catalog, SIM Inventory,
Number Portability, IMEI Registry, Device Inventory, Billing Profile) use the
simpler `lookup()` contract instead — see data_source_adapter.py.
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class EligibilityResponse(TypedDict):
    fixable: bool
    reasoning: str
    recommended_action: str  # "FETCH" | "ESCALATE"


class ProvisionResponse(TypedDict):
    success: bool
    reference_id: str
    status: str
    error_type: str | None  # e.g. "BACKEND_ERROR" if the adapter itself failed
    message: str


class StatusResponse(TypedDict):
    reference_id: str
    status: str
    details: dict[str, Any]


class PartnerAdapter(Protocol):
    """Contract that all partner-style mock adapters must implement."""

    def check_eligibility(self, request: dict[str, Any]) -> EligibilityResponse:
        """Determine whether a failure is fetchable/fixable or a hard business-rule block."""
        ...

    def provision(self, request: dict[str, Any]) -> ProvisionResponse:
        """Attempt to (re)provision/activate the subscription item with this partner."""
        ...

    def get_status(self, reference_id: str) -> StatusResponse:
        """Retrieve the current status of a previously provisioned item."""
        ...


def structured_error(error_type: str, message: str) -> ProvisionResponse:
    """Helper for adapters to return a structured error response rather than
    raising an unhandled exception (per NFR pattern: 'structured error responses
    from mock adapters')."""
    return ProvisionResponse(
        success=False,
        reference_id="",
        status="ERROR",
        error_type=error_type,
        message=message,
    )
