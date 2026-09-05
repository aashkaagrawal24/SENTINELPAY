from datetime import UTC, datetime, timedelta

from app.services.merchant_services import MerchantPolicyService


def test_active_policy_prefers_product_and_latest_version():
    now = datetime.now(UTC)
    base = {"status": "ACTIVE", "valid_from": now - timedelta(days=1), "valid_until": None}
    policies = [
        {**base, "scope": "GLOBAL", "scope_reference": None, "version": 4, "id": "global"},
        {
            **base,
            "scope": "CATEGORY",
            "scope_reference": "Headphones",
            "version": 2,
            "id": "category",
        },
        {**base, "scope": "PRODUCT", "scope_reference": "xm4", "version": 1, "id": "product"},
    ]
    assert MerchantPolicyService.select_active(policies, "xm4", "Headphones")["id"] == "product"


def test_expired_policy_not_selected():
    now = datetime.now(UTC)
    policies = [
        {
            "status": "ACTIVE",
            "scope": "GLOBAL",
            "scope_reference": None,
            "version": 1,
            "valid_from": now - timedelta(days=2),
            "valid_until": now - timedelta(days=1),
        }
    ]
    assert MerchantPolicyService.select_active(policies, "x", "y", now) is None
