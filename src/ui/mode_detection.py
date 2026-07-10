"""
Mode detection — reads the deployed OrderPlacementService Lambda's
OPERATING_MODE environment variable, per business-logic-model.md's resolution
of BR-37. Read-only permission (lambda:GetFunctionConfiguration), no secrets.
"""

from __future__ import annotations

from ui.aws_clients import get_lambda_client

_ORDER_PLACEMENT_FUNCTION_NAME = "ora-order-placement-service"


def get_operating_mode() -> str:
    """Returns 'REALISTIC' or 'DEMO'. Defaults to 'REALISTIC' if the function
    configuration can't be read (e.g., local dev without the Lambda deployed yet)."""
    try:
        client = get_lambda_client()
        config = client.get_function_configuration(FunctionName=_ORDER_PLACEMENT_FUNCTION_NAME)
        return config.get("Environment", {}).get("Variables", {}).get("OPERATING_MODE", "REALISTIC")
    except Exception:
        return "REALISTIC"
