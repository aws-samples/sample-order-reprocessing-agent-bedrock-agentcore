"""
Mock Netflix Partner Adapter — simulates Netflix's provisioning API.
Implements the PartnerAdapter contract.

Failure mode: entitlement provisioning failure (fetchable/fixable via retry).

Per components.md (2.8), infrastructure-design.md (Lambda: ora-adapter-netflix).
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

_ENTITLEMENT_FAILURE_RATE = 0.4  # elevated to make the scenario reproducible in demos
_STATUS_STORE: dict[str, str] = {}


def check_eligibility(request: dict[str, Any]) -> EligibilityResponse:
    return EligibilityResponse(
        fixable=True,
        reasoning="Netflix entitlement provisioning failures are transient and resolve on retry",
        recommended_action="FETCH",
    )


def provision(request: dict[str, Any]) -> ProvisionResponse:
    subscription_id = request.get("subscription_id", "")
    retry_attempt = request.get("retry_attempt", 0)

    # Fail on first attempt (simulating entitlement provisioning failure),
    # succeed on retry — matches "auto-resolved via partner API retry" (FR test scenario 6).
    if retry_attempt == 0 and random.random() < _ENTITLEMENT_FAILURE_RATE:  # nosec B311 -- simulated transient failure, not crypto
        return structured_error(
            "ENTITLEMENT_FAILURE",
            "Netflix entitlement not yet provisioned — retry required",
        )

    reference_id = str(uuid.uuid4())
    _STATUS_STORE[reference_id] = "ACTIVE"

    return ProvisionResponse(
        success=True,
        reference_id=reference_id,
        status="ACTIVE",
        error_type=None,
        message=f"Netflix entitlement provisioned for subscription {subscription_id}",
    )


def get_status(reference_id: str) -> StatusResponse:
    return StatusResponse(
        reference_id=reference_id,
        status=_STATUS_STORE.get(reference_id, "UNKNOWN"),
        details={},
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    action = event.get("action")
    if action == "check_eligibility":
        return dict(check_eligibility(event.get("request", {})))
    if action == "provision":
        return dict(provision(event.get("request", {})))
    if action == "get_status":
        return dict(get_status(event.get("reference_id", "")))
    return structured_error("INVALID_ACTION", f"Unknown action: {action!r}")
