"""
Mock Disney+ Partner Adapter — simulates Disney+'s provisioning API.
Implements the PartnerAdapter contract.

Failure mode: region licensing lock — a HARD business-rule block, NOT fetchable.
check_eligibility() correctly reports fixable=False, recommended_action="ESCALATE"
per BR-9 (non-fetchable scenarios are tagged so CheckVASEligibility, Unit 2,
never wastes a fetch attempt).

Per components.md (2.10), infrastructure-design.md (Lambda: ora-adapter-disneyplus).
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

# Regions where Disney+ (mock) content licensing is unavailable — simulates a
# real region-lock business constraint that cannot be resolved by fetching data.
_UNLICENSED_REGIONS = {"region_x", "region_y"}


def check_eligibility(request: dict[str, Any]) -> EligibilityResponse:
    region = request.get("region", "")
    if region in _UNLICENSED_REGIONS:
        return EligibilityResponse(
            fixable=False,
            reasoning=f"Disney+ content licensing is not available in region '{region}' — "
                      "this is a business/legal constraint, not a data-fetch problem",
            recommended_action="ESCALATE",
        )
    return EligibilityResponse(
        fixable=True,
        reasoning="No region lock detected; provisioning can proceed",
        recommended_action="FETCH",
    )


def provision(request: dict[str, Any]) -> ProvisionResponse:
    subscription_id = request.get("subscription_id", "")
    region = request.get("region", "")

    if region in _UNLICENSED_REGIONS:
        return structured_error(
            "REGION_LOCK",
            f"Disney+ provisioning rejected — region '{region}' is not licensed",
        )

    reference_id = str(uuid.uuid4())
    _STATUS_STORE[reference_id] = "ACTIVE"

    return ProvisionResponse(
        success=True,
        reference_id=reference_id,
        status="ACTIVE",
        error_type=None,
        message=f"Disney+ Premium provisioned for subscription {subscription_id}",
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
