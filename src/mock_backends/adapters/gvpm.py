"""
Mock GVPM Adapter — simulates Amdocs Service Orchestration (GVPM), TMF641-style
order resubmission for Core Telco and Device subscription items. Implements
the full PartnerAdapter contract.

Per components.md (2.1), component-methods.md (resubmit_order_item),
infrastructure-design.md (Lambda: ora-adapter-gvpm).
"""

from __future__ import annotations

import random
import uuid
from typing import Any

from mock_backends.shared.partner_adapter import (
    EligibilityResponse,
    ProvisionResponse,
    StatusResponse,
    structured_error,
)

# Simulated occasional transient backend error rate, to exercise the
# BACKEND_ERROR history event path (BR-10 / original proposal Scenario 2).
_SIMULATED_BACKEND_ERROR_RATE = 0.05

_STATUS_STORE: dict[str, str] = {}


def check_eligibility(request: dict[str, Any]) -> EligibilityResponse:
    """GVPM-side eligibility is generally fixable via data fetch — hard business
    rule blocks for Core Telco/Device are handled by the device-specific checks
    (trade-in valuation, IMEI blacklist) rather than GVPM itself."""
    return EligibilityResponse(
        fixable=True,
        reasoning="GVPM order fallout is resolvable by resubmitting with corrected fields",
        recommended_action="FETCH",
    )


def provision(request: dict[str, Any]) -> ProvisionResponse:
    """resubmit_order_item(subscription_id, corrected_fields) equivalent —
    per component-methods.md, this is GVPM's `resubmit_order_item`."""
    subscription_id = request.get("subscription_id", "")

    if random.random() < _SIMULATED_BACKEND_ERROR_RATE:  # nosec B311 -- simulated transient failure, not crypto
        return structured_error("BACKEND_ERROR", "GVPM service temporarily unavailable (simulated)")

    reference_id = str(uuid.uuid4())
    _STATUS_STORE[reference_id] = "SUCCESS"

    return ProvisionResponse(
        success=True,
        reference_id=reference_id,
        status="SUCCESS",
        error_type=None,
        message=f"Order item {subscription_id} resubmitted to GVPM via TMF641 — activation confirmed",
    )


def get_status(reference_id: str) -> StatusResponse:
    return StatusResponse(
        reference_id=reference_id,
        status=_STATUS_STORE.get(reference_id, "UNKNOWN"),
        details={},
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. Expects event = {"action": "check_eligibility"|"provision"|"get_status", ...}."""
    action = event.get("action")
    if action == "check_eligibility":
        return dict(check_eligibility(event.get("request", {})))
    if action == "provision":
        return dict(provision(event.get("request", {})))
    if action == "get_status":
        return dict(get_status(event.get("reference_id", "")))
    return structured_error("INVALID_ACTION", f"Unknown action: {action!r}")
