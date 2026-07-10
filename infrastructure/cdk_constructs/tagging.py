"""
Shared tagging helper — applies the mandatory tag set (NFR-3) to any CDK
construct/stack, used across all units per the "mandatory, not optional"
isolation strategy established in requirements.md (shared-account deployment).
"""

from __future__ import annotations

from datetime import date

from aws_cdk import Tags
from constructs import Construct


def apply_standard_tags(
    scope: Construct,
    component: str,
    environment: str = "Demo",
) -> None:
    """Apply the standard tag set (NFR-3) to a construct and everything nested
    within it. `component` should be one of: mock-backend, agent,
    order-placement-service, ui, infrastructure.

    NOTE: Owner, CostCenter, and Workshop-Attendee-ID are intentionally NOT
    set here — they are applied once at the STACK level (in infrastructure/
    app.py) and allowed to cascade down. CDK's tag precedence favors
    more-specific (child construct) tags over less-specific (parent/stack)
    tags when the same key is set at both levels — so if this function also
    set Owner/CostCenter with a hardcoded "unspecified" default, that would
    silently override the stack-level value passed via CDK context, which is
    exactly the bug this comment is here to prevent from being reintroduced."""
    Tags.of(scope).add("Project", "OrderReprocessingAgent")
    Tags.of(scope).add("Environment", environment)
    Tags.of(scope).add("Component", component)
    Tags.of(scope).add("CreatedDate", date.today().isoformat())
    Tags.of(scope).add("ManagedBy", "CDK")
