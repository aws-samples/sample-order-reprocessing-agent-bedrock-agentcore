"""
Mock Ticketing Adapter — simulates ServiceNow/Jira escalation ticket creation.
Called by EscalateToHuman (Unit 2, tool 1.6).

Per components.md (2.12), component-methods.md (create_ticket),
infrastructure-design.md (Lambda: ora-adapter-ticketing).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict


class TicketResponse(TypedDict):
    ticket_id: str
    created: bool
    created_at: str


_TICKET_STORE: dict[str, dict[str, Any]] = {}


def create_ticket(diagnosis: dict[str, Any]) -> TicketResponse:
    """diagnosis: full DiagnosisPackage — order record, attempted fixes,
    downstream error details, and the agent's reasoning/recommended next action."""
    ticket_id = f"TICKET-{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now(timezone.utc).isoformat()

    _TICKET_STORE[ticket_id] = {
        "diagnosis": diagnosis,
        "created_at": created_at,
        "status": "OPEN",
    }

    return TicketResponse(ticket_id=ticket_id, created=True, created_at=created_at)


def get_ticket(ticket_id: str) -> dict[str, Any] | None:
    return _TICKET_STORE.get(ticket_id)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    result = create_ticket(event.get("diagnosis", {}))
    return dict(result)
