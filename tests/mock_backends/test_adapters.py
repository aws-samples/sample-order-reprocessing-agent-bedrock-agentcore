"""Unit tests for the 12 mock backend adapters (mock_backends/adapters/*.py).

Covers: data-source adapters' lookup() contract, partner adapters'
check_eligibility/provision/get_status contract, and the BACKEND_ERROR /
non-fetchable (region lock, trade-in dispute) paths.
"""

from __future__ import annotations

from mock_backends.adapters import (
    billing_profile,
    device_inventory,
    disneyplus,
    esim_provisioning,
    gvpm,
    imei_registry,
    netflix,
    number_portability,
    product_catalog,
    sim_inventory,
    spotify,
    ticketing,
)
from mock_backends.shared.domain_models import StockStatus


# --- Data-source adapters ---

def test_esim_provisioning_lookup_generates_and_caches_activation_code():
    result1 = esim_provisioning.lookup("ICCID-123")
    result2 = esim_provisioning.lookup("ICCID-123")
    assert result1["success"] is True
    assert result1["value"] == result2["value"]  # cached, not regenerated


def test_esim_provisioning_lookup_requires_key():
    result = esim_provisioning.lookup("")
    assert result["success"] is False
    assert result["error_type"] == "NOT_FOUND"


def test_product_catalog_lookup_known_plan():
    result = product_catalog.lookup("postpaid-5g-unlimited")
    assert result["success"] is True
    assert result["value"] == "POST5G999"


def test_sim_inventory_lookup_generates_valid_iccid_format():
    result = sim_inventory.lookup("SUB-1")
    assert result["success"] is True
    assert result["value"].startswith("8991")
    assert len(result["value"]) == 19


def test_number_portability_lookup_generates_msisdn():
    result = number_portability.lookup("SUB-1")
    assert result["success"] is True
    assert result["value"].startswith("9198")


def test_imei_registry_valid_by_default():
    result = imei_registry.lookup("IMEI-999")
    assert result["success"] is True
    assert result["value"] == "VALID"


def test_imei_registry_blacklisted_imei_fails():
    imei_registry.mark_blacklisted("IMEI-BAD")
    result = imei_registry.lookup("IMEI-BAD")
    assert result["success"] is False
    assert result["error_type"] == "VALIDATION_FAILED"


def test_device_inventory_returns_shared_static_status(dynamodb_tables):
    result1 = device_inventory.lookup("Samsung Galaxy Z Fold 6")
    result2 = device_inventory.lookup("Samsung Galaxy Z Fold 6")
    assert result1["value"] == result2["value"] == StockStatus.BACKORDER.value


def test_device_inventory_set_stock_status_helper(dynamodb_tables):
    device_inventory.set_stock_status("Test Model X", StockStatus.IN_STOCK)
    result = device_inventory.lookup("Test Model X")
    assert result["value"] == StockStatus.IN_STOCK.value


def test_billing_profile_missing_by_default():
    result = billing_profile.lookup("CUST-NEW")
    assert result["success"] is False
    assert result["error_type"] == "BILLING_PROFILE_MISSING"


def test_billing_profile_linked_customer_resolves():
    billing_profile.link_billing_profile("CUST-LINKED", "BILL-001")
    result = billing_profile.lookup("CUST-LINKED")
    assert result["success"] is True
    assert result["value"] == "BILL-001"


def test_billing_profile_trade_in_dispute_helper():
    assert billing_profile.check_trade_in_dispute("ORD-X") is False
    billing_profile.mark_trade_in_disputed("ORD-X")
    assert billing_profile.check_trade_in_dispute("ORD-X") is True


# --- Partner adapters (full PartnerAdapter contract) ---

def test_gvpm_check_eligibility_always_fixable():
    result = gvpm.check_eligibility({})
    assert result["fixable"] is True
    assert result["recommended_action"] == "FETCH"


def test_gvpm_provision_success_shape():
    result = gvpm.provision({"subscription_id": "SUB-1"})
    # Either succeeds or simulates a backend error — both are structurally valid.
    assert "success" in result
    assert "reference_id" in result
    if result["success"]:
        assert result["status"] == "SUCCESS"
    else:
        assert result["error_type"] == "BACKEND_ERROR"


def test_netflix_provision_retry_succeeds():
    # retry_attempt=1 should never hit the simulated first-attempt failure path
    result = netflix.provision({"subscription_id": "SUB-2", "retry_attempt": 1})
    assert result["success"] is True
    assert result["status"] == "ACTIVE"


def test_spotify_provision_fails_without_billing_profile():
    result = spotify.provision({"subscription_id": "SUB-3"})
    assert result["success"] is False
    assert result["error_type"] == "BILLING_PROFILE_MISSING"


def test_spotify_provision_succeeds_with_billing_profile():
    result = spotify.provision({"subscription_id": "SUB-3", "billing_profile_id": "BILL-002"})
    assert result["success"] is True


def test_disneyplus_check_eligibility_region_lock_is_non_fetchable():
    result = disneyplus.check_eligibility({"region": "region_x"})
    assert result["fixable"] is False
    assert result["recommended_action"] == "ESCALATE"


def test_disneyplus_check_eligibility_normal_region_is_fixable():
    result = disneyplus.check_eligibility({"region": "region_normal"})
    assert result["fixable"] is True


def test_disneyplus_provision_rejected_in_locked_region():
    result = disneyplus.provision({"subscription_id": "SUB-4", "region": "region_y"})
    assert result["success"] is False
    assert result["error_type"] == "REGION_LOCK"


def test_ticketing_create_ticket_returns_id():
    result = ticketing.create_ticket({"order_id": "ORD-1", "reason": "unresolvable"})
    assert result["created"] is True
    assert result["ticket_id"].startswith("TICKET-")
    stored = ticketing.get_ticket(result["ticket_id"])
    assert stored is not None
    assert stored["diagnosis"]["order_id"] == "ORD-1"


def test_handler_invalid_action_returns_structured_error():
    result = gvpm.handler({"action": "bogus"}, None)
    assert result["success"] is False
    assert result["error_type"] == "INVALID_ACTION"
