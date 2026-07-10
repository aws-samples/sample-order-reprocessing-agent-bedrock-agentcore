"""
EscalateToHuman tool — creates a human-actionable ticket when an issue cannot
be auto-resolved. Builds a full DiagnosisPackage, invokes Unit 1's Mock
Ticketing Adapter, publishes to SNS.

Per components.md (1.6), business-rules.md BR-18.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.shared.tool_types import DiagnosisPackage, EscalationResult
from mock_backends.adapters import ticketing
from mock_backends.repository import history_repository, orders_repository
from mock_backends.shared.domain_models import HistoryEvent, HistoryEventType, OrderStatus


def escalate_to_human(diagnosis: DiagnosisPackage) -> EscalationResult:
    """BR-18: always populates the full DiagnosisPackage, even if attempted_fixes
    is empty (immediate escalation per BR-17)."""
    ticket_response = ticketing.create_ticket(
        {
            "order_id": diagnosis.order_id,
            "subscription_id": diagnosis.subscription_id,
            "order_snapshot": diagnosis.order_snapshot,
            "failure_reason": diagnosis.failure_reason,
            "agent_reasoning": diagnosis.agent_reasoning,
            "recommended_action": diagnosis.recommended_action,
            "attempted_fixes": diagnosis.attempted_fixes,
            "downstream_error": diagnosis.downstream_error,
        }
    )

    # Notify (SNS publish happens at the infrastructure/Lambda-config level in
    # deployment; here we record the intent and treat as notified in v1's mock).
    notified = True

    # Escalation always drives the parent order to ESCALATED, overriding the
    # normal derive_order_status() computation (per order_status_service's
    # apply_escalation() special case).
    orders_repository.update_order_status(diagnosis.order_id, OrderStatus.ESCALATED, datetime.now(timezone.utc).isoformat())

    history_repository.record_history_event(
        HistoryEvent(
            order_id=diagnosis.order_id,
            subscription_id=diagnosis.subscription_id,
            event_type=HistoryEventType.ESCALATED,
            tool_name="EscalateToHuman",
            summary=f"Escalated to human: {diagnosis.failure_reason}. Ticket {ticket_response['ticket_id']} created.",
            resulting_status=OrderStatus.ESCALATED.value,
            details={
                "ticket_id": ticket_response["ticket_id"],
                "attempted_fixes": diagnosis.attempted_fixes,
                "agent_reasoning": diagnosis.agent_reasoning,
            },
        )
    )

    return EscalationResult(
        ticket_id=ticket_response["ticket_id"],
        order_id=diagnosis.order_id,
        subscription_id=diagnosis.subscription_id,
        notified=notified,
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. Expects event matching DiagnosisPackage's fields."""
    diagnosis = DiagnosisPackage(
        order_id=event["order_id"],
        subscription_id=event["subscription_id"],
        order_snapshot=event.get("order_snapshot", {}),
        failure_reason=event.get("failure_reason", ""),
        agent_reasoning=event.get("agent_reasoning", ""),
        recommended_action=event.get("recommended_action", ""),
        attempted_fixes=event.get("attempted_fixes", []),
        downstream_error=event.get("downstream_error"),
    )
    result = escalate_to_human(diagnosis)
    return {
        "ticket_id": result.ticket_id,
        "order_id": result.order_id,
        "subscription_id": result.subscription_id,
        "notified": result.notified,
    }
