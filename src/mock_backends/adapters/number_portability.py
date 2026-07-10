"""
Mock Number Portability Adapter — source of truth for msisdn values.
Implements DataSourceAdapter contract.

Per components.md (2.5), infrastructure-design.md (Lambda: ora-adapter-number-portability).
"""

from __future__ import annotations

import random
from typing import Any

from mock_backends.shared.data_source_adapter import LookupResponse

_MOCK_DB: dict[str, str] = {}


def _generate_msisdn() -> str:
    return "9198" + "".join(str(random.randint(0, 9)) for _ in range(8))  # nosec B311 -- fake mock backend data, not crypto


def lookup(key: str) -> LookupResponse:
    """key = subscription_id used to look up (or newly allocate) an msisdn."""
    if not key:
        return LookupResponse(
            success=False, key=key, value=None,
            error_type="NOT_FOUND", message="A subscription reference is required to look up an msisdn",
        )

    if key not in _MOCK_DB:
        _MOCK_DB[key] = _generate_msisdn()

    return LookupResponse(
        success=True, key=key, value=_MOCK_DB[key], error_type=None,
        message="msisdn resolved from Number Portability DB",
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    result = lookup(event.get("key", ""))
    return dict(result)
