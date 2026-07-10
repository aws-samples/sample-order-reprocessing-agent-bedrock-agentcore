"""
Mock IMEI Registry Adapter — validates/resolves device IMEI values, simulating
network blacklist checks. Implements DataSourceAdapter contract.

Per components.md (2.6), business-rules.md (device IMEI validation failure scenario),
infrastructure-design.md (Lambda: ora-adapter-imei-registry).
"""

from __future__ import annotations

import random
from typing import Any

from mock_backends.shared.data_source_adapter import LookupResponse

# Simulate a small blacklist of IMEIs that will always fail validation,
# to make the "imei_validation_failure" scenario deterministically reproducible
# in Demo Mode when needed, while most IMEIs pass validation normally.
_SIMULATED_BLACKLIST: set[str] = set()


def lookup(key: str) -> LookupResponse:
    """key = IMEI. Returns validation status: whether the IMEI is recognized/clean."""
    if not key:
        return LookupResponse(
            success=False, key=key, value=None,
            error_type="NOT_FOUND", message="IMEI is required for validation",
        )

    if key in _SIMULATED_BLACKLIST:
        return LookupResponse(
            success=False, key=key, value="BLACKLISTED", error_type="VALIDATION_FAILED",
            message="IMEI is blacklisted / not recognized by the network",
        )

    return LookupResponse(
        success=True, key=key, value="VALID", error_type=None,
        message="IMEI validated successfully against the network registry",
    )


def mark_blacklisted(imei: str) -> None:
    """Test/Demo-Mode helper to deterministically force an IMEI validation failure."""
    _SIMULATED_BLACKLIST.add(imei)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    result = lookup(event.get("key", ""))
    return dict(result)
