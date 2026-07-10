"""
CheckVASEligibility tool — determines whether a VAS or device failure is
fetchable/fixable versus a hard business-rule block. Dispatches to the
relevant Unit 1 PartnerAdapter's check_eligibility() (BR-16/BR-17: checked
BEFORE any fetch attempt).

Per components.md (1.4), business-rules.md BR-16/BR-17.
"""

from __future__ import annotations

from typing import Any

from mock_backends.adapters import billing_profile, disneyplus, gvpm, netflix, spotify
from mock_backends.repository import history_repository
from mock_backends.shared.domain_models import HistoryEvent, HistoryEventType

_PARTNER_DISPATCH = {
    "Netflix": netflix.check_eligibility,
    "Spotify": spotify.check_eligibility,
    "Disney+": disneyplus.check_eligibility,
    "Mobile Line": gvpm.check_eligibility,
    "Device Purchase/Financing": gvpm.check_eligibility,
}


def check_vas_eligibility(order_id: str, subscription_id: str, subscription_type: str, request: dict) -> dict:
    """Returns an EligibilityResponse-shaped dict: {fixable, reasoning, recommended_action}.

    For device trade-in disputes specifically, checks Unit 1's Billing Profile
    Adapter's dispute tracking (business_logic_summary.md's trade-in mismatch
    scenario) in addition to the general partner eligibility check."""
    if subscription_type == "Device Purchase/Financing" and billing_profile.check_trade_in_dispute(order_id):
        result = {
            "fixable": False,
            "reasoning": "Trade-in valuation is disputed — this is a business/legal constraint, "
                         "not a data-fetch problem",
            "recommended_action": "ESCALATE",
        }
    else:
        eligibility_fn = _PARTNER_DISPATCH.get(subscription_type, gvpm.check_eligibility)
        result = dict(eligibility_fn(request))

    history_repository.record_history_event(
        HistoryEvent(
            order_id=order_id,
            subscription_id=subscription_id,
            event_type=HistoryEventType.VALIDATED,  # eligibility check is part of validation/diagnosis
            tool_name="CheckVASEligibility",
            summary=f"Eligibility check for {subscription_type}: "
                    f"{'fixable' if result['fixable'] else 'NOT fixable — ' + result['reasoning']}",
            resulting_status="FAILED",
            details=result,
        )
    )

    return result


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. Expects event = {"order_id", "subscription_id",
    "subscription_type", "request": {...partner-specific context, e.g. region}}."""
    return check_vas_eligibility(
        order_id=event["order_id"],
        subscription_id=event["subscription_id"],
        subscription_type=event["subscription_type"],
        request=event.get("request", {}),
    )
