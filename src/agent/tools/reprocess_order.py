"""
ReprocessOrder tool — resubmits a corrected subscription item for activation.
Routes to the correct downstream mock adapter (GVPM for Core Telco/Device,
partner API for VAS), performs an idempotent status transition (BR-19,
reusing Unit 1's transition_status_idempotent), and recomputes the parent
order's derived status.

Per components.md (1.5), business-rules.md BR-19.
**Guardrails scope (BR-20)**: this tool's input is the one Bedrock Guardrails
intercepts — see guardrails/reprocess_order_guardrail.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.shared.tool_types import ReprocessResult
from mock_backends.adapters import disneyplus, gvpm, netflix, spotify
from mock_backends.repository import history_repository, order_status_service, subscriptions_repository
from mock_backends.shared.domain_models import HistoryEvent, HistoryEventType, SubscriptionStatus

_PROVISION_DISPATCH = {
    "Netflix": netflix.provision,
    "Spotify": spotify.provision,
    "Disney+": disneyplus.provision,
    "Mobile Line": gvpm.provision,
    "Device Purchase/Financing": gvpm.provision,
}


def reprocess_order(
    order_id: str, subscription_id: str, subscription_type: str, updated_fields: dict, request: dict
) -> ReprocessResult:
    """Resubmits the corrected subscription. Idempotent per BR-19: if the
    subscription is already ACTIVATED (e.g., from a prior successful attempt
    that this call is a retry of), the conditional write is skipped rather
    than re-submitting to the downstream system a second time."""
    # Persist the newly-fetched field values before attempting resubmission.
    if updated_fields:
        subscriptions_repository.update_subscription_fields(order_id, subscription_id, updated_fields)

    provision_fn = _PROVISION_DISPATCH.get(subscription_type, gvpm.provision)
    downstream_response = dict(provision_fn(request))

    if downstream_response.get("success"):
        applied = subscriptions_repository.transition_status_idempotent(
            order_id, subscription_id, SubscriptionStatus.ACTIVATED,
            allowed_current_statuses=[SubscriptionStatus.FAILED, SubscriptionStatus.PENDING],
        )
        result = ReprocessResult(
            subscription_id=subscription_id, status="ACTIVATED",
            downstream_response=downstream_response, idempotent_skip=not applied,
        )
    else:
        result = ReprocessResult(
            subscription_id=subscription_id, status="FAILED",
            downstream_response=downstream_response, idempotent_skip=False,
        )

    new_order_status = order_status_service.recompute_and_persist_order_status(
        order_id, updated_at=datetime.now(timezone.utc).isoformat()
    )

    history_repository.record_history_event(
        HistoryEvent(
            order_id=order_id,
            subscription_id=subscription_id,
            event_type=HistoryEventType.REPROCESSED,
            tool_name="ReprocessOrder",
            summary=f"Reprocessed {subscription_id}: {result.status}"
                    + (" (idempotent no-op — already activated)" if result.idempotent_skip else ""),
            resulting_status=new_order_status.value,
            details={"downstream_response": downstream_response, "idempotent_skip": result.idempotent_skip},
        )
    )

    return result


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. Expects event = {"order_id", "subscription_id",
    "subscription_type", "updated_fields": {...}, "request": {...}}.

    NOTE: This is the tool whose input Bedrock Guardrails intercepts (BR-20) —
    `updated_fields` values must be traceable to a prior FetchMissingData
    result, not agent-fabricated, before this handler is invoked."""
    result = reprocess_order(
        order_id=event["order_id"],
        subscription_id=event["subscription_id"],
        subscription_type=event["subscription_type"],
        updated_fields=event.get("updated_fields", {}),
        request=event.get("request", {}),
    )
    return {
        "subscription_id": result.subscription_id,
        "status": result.status,
        "downstream_response": result.downstream_response,
        "idempotent_skip": result.idempotent_skip,
    }
