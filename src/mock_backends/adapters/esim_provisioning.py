"""
Mock eSIM Provisioning Adapter — source of truth for activation_code values,
keyed by ICCID. Implements DataSourceAdapter contract.

Per components.md (2.2), component-methods.md, infrastructure-design.md
(Lambda: ora-adapter-esim-provisioning).
"""

from __future__ import annotations

import random
import string
from typing import Any

from mock_backends.shared.data_source_adapter import LookupResponse

# In-memory mock "database" keyed by ICCID -> activation_code.
# In a real deployment this would be a DynamoDB table; kept in-memory here
# since this is a fully-mocked v1 backend (per requirements.md Section 4.4/Deferred).
_MOCK_DB: dict[str, str] = {}


def _generate_activation_code() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"LPA:1$rsp.provider.com${suffix}"


def lookup(key: str) -> LookupResponse:
    """key = ICCID. Returns (and lazily generates, simulating a provisioned
    but not-yet-synced record) the activation_code for that ICCID."""
    if not key:
        return LookupResponse(
            success=False, key=key, value=None,
            error_type="NOT_FOUND", message="ICCID is required to look up an activation code",
        )

    if key not in _MOCK_DB:
        _MOCK_DB[key] = _generate_activation_code()

    return LookupResponse(
        success=True, key=key, value=_MOCK_DB[key], error_type=None,
        message="activation_code resolved from eSIM Provisioning DB",
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. Expects event = {"key": "<iccid>"}."""
    result = lookup(event.get("key", ""))
    return dict(result)
