"""
Mock Spotify Partner Adapter — simulates Spotify's provisioning API.
Implements the PartnerAdapter contract.

Failure mode: billing profile not linked (fetchable via Billing Profile Adapter).

Per components.md (2.9), infrastructure-design.md (Lambda: ora-adapter-spotify).
"""

from __future__ import annotations

import uuid
from typing import Any

from mock_backends.shared.partner_adapter import (
    EligibilityResponse,
    ProvisionResponse,
    StatusResponse,
    structured_error,
)

_STATUS_STORE: dict[str, str] = {}


def check_eligibility(request: dict[str, Any]) -> EligibilityResponse:
    return EligibilityResponse(
        fixable=True,
        reasoning="Missing billing profile linkage is resolvable by fetching from Billing Profile Adapter",
        recommended_action="FETCH",
    )


def provision(request: dict[str, Any]) -> ProvisionResponse:
    subscription_id = request.get("subscription_id", "")
    billing_profile_id = request.get("billing_profile_id")

    if not billing_profile_id:
        return structured_error(
            "BILLING_PROFILE_MISSING",
            "Spotify Premium requires a linked billing profile — none found for this customer",
        )

    reference_id = str(uuid.uuid4())
    _STATUS_STORE[reference_id] = "ACTIVE"

    return ProvisionResponse(
        success=True,
        reference_id=reference_id,
        status="ACTIVE",
        error_type=None,
        message=f"Spotify Premium provisioned for subscription {subscription_id}",
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
