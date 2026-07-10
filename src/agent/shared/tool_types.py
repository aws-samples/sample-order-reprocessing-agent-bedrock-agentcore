"""
Shared tool response types for Unit 2 (Agent Tools & Orchestration).

Per domain-entities.md: ValidationResult, MissingItem, FetchResult,
DiagnosisPackage, EscalationResult. Builds on Unit 1's Order/Subscription/
HistoryEvent domain models (imported directly, no duplication).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MissingItem:
    subscription_id: str
    missing_field: str
    fetch_from: str  # which Unit 1 adapter/provider resolves this field


@dataclass
class ValidationResult:
    order_id: str
    missing_items: list[MissingItem] = field(default_factory=list)

    @property
    def all_valid(self) -> bool:
        return len(self.missing_items) == 0


@dataclass
class FetchResult:
    subscription_id: str
    field: str
    value: Any
    source: str
    success: bool
    error_type: Optional[str] = None
    message: str = ""


@dataclass
class DiagnosisPackage:
    """Per Q3: A — formally-typed dataclass, passed to EscalateToHuman."""

    order_id: str
    subscription_id: str
    order_snapshot: dict[str, Any]
    failure_reason: str
    agent_reasoning: str
    recommended_action: str
    attempted_fixes: list[str] = field(default_factory=list)
    downstream_error: Optional[dict[str, Any]] = None


@dataclass
class ReprocessResult:
    subscription_id: str
    status: str  # "ACTIVATED" | "FAILED"
    downstream_response: dict[str, Any] = field(default_factory=dict)
    idempotent_skip: bool = False


@dataclass
class EscalationResult:
    ticket_id: str
    order_id: str
    subscription_id: str
    notified: bool
