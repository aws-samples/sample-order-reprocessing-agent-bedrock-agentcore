"""Unit tests for order_history tab logic and mode_detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mock_backends.repository import history_repository
from mock_backends.shared.domain_models import HistoryEvent, HistoryEventType
from ui.mode_detection import get_operating_mode
from ui.tabs.order_history import get_order_history


def test_get_order_history_returns_chronological_events(dynamodb_tables):
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-1", event_type=HistoryEventType.DETECTED,
            tool_name="GetOrderDetails", summary="Order failed", resulting_status="FAILED",
            event_timestamp="2026-01-01T00:00:01Z",
        )
    )
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-1", event_type=HistoryEventType.VALIDATED,
            tool_name="ValidateOrder", summary="Missing field", resulting_status="FAILED",
            event_timestamp="2026-01-01T00:00:02Z",
        )
    )

    history = get_order_history("ORD-1")
    assert len(history) == 2
    assert history[0]["event_type"] == "DETECTED"
    assert history[1]["event_type"] == "VALIDATED"


def test_get_order_history_includes_details_field(dynamodb_tables):
    """Real gap found while demoing to a team: `details` (which contains the
    actual missing-field names, fetch sources, and agent reasoning) was
    silently dropped by both the logic function and the UI rendering — only
    `summary`'s terse one-liner was ever shown. This test locks in that
    `details` is now correctly passed through."""
    history_repository.record_history_event(
        HistoryEvent(
            order_id="ORD-2", event_type=HistoryEventType.VALIDATED,
            tool_name="ValidateOrder", summary="Validation found 1 missing field(s)",
            resulting_status="FAILED", event_timestamp="2026-01-01T00:00:01Z",
            details={
                "missing_items": [
                    {"subscription_id": "SUB-1", "missing_field": "activation_code", "fetch_from": "eSIM Provisioning DB"}
                ]
            },
        )
    )

    history = get_order_history("ORD-2")
    assert len(history) == 1
    assert history[0]["details"]["missing_items"][0]["missing_field"] == "activation_code"
    assert history[0]["details"]["missing_items"][0]["fetch_from"] == "eSIM Provisioning DB"


def test_get_order_history_empty_for_unknown_order(dynamodb_tables):
    history = get_order_history("ORD-DOES-NOT-EXIST")
    assert history == []


@patch("ui.mode_detection.get_lambda_client")
def test_get_operating_mode_reads_lambda_env_var(mock_get_client):
    mock_client = MagicMock()
    mock_client.get_function_configuration.return_value = {
        "Environment": {"Variables": {"OPERATING_MODE": "DEMO"}}
    }
    mock_get_client.return_value = mock_client

    mode = get_operating_mode()
    assert mode == "DEMO"


@patch("ui.mode_detection.get_lambda_client")
def test_get_operating_mode_defaults_to_realistic_on_error(mock_get_client):
    mock_get_client.side_effect = Exception("Lambda not found")

    mode = get_operating_mode()
    assert mode == "REALISTIC"
