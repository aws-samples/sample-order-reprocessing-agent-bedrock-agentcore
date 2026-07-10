"""
Mock SIM Inventory Adapter — source of truth for ICCID values.
Implements DataSourceAdapter contract.

Per components.md (2.4), infrastructure-design.md (Lambda: ora-adapter-sim-inventory).
"""

from __future__ import annotations

import random
from typing import Any

from mock_backends.shared.data_source_adapter import LookupResponse

_MOCK_DB: dict[str, str] = {}


def _generate_iccid() -> str:
    return "8991" + "".join(str(random.randint(0, 9)) for _ in range(15))  # nosec B311 -- fake mock backend data, not crypto


def lookup(key: str) -> LookupResponse:
    """key = subscription_id or msisdn used to look up the assigned ICCID."""
    if not key:
        return LookupResponse(
            success=False, key=key, value=None,
            error_type="NOT_FOUND", message="A subscription reference is required to look up ICCID",
        )

    if key not in _MOCK_DB:
        _MOCK_DB[key] = _generate_iccid()

    return LookupResponse(
        success=True, key=key, value=_MOCK_DB[key], error_type=None,
        message="iccid resolved from SIM Inventory DB",
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    result = lookup(event.get("key", ""))
    return dict(result)
