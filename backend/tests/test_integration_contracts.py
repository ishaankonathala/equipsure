from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.integrations.base import (
    BILLINGCENTER_SOURCE,
    CLAIMCENTER_SOURCE,
    POLICYCENTER_SOURCE,
    BillingCenterService,
    ClaimCenterService,
    IntegrationResult,
    PolicyCenterService,
)


def test_result_requires_source():
    with pytest.raises(ValueError, match="source is required"):
        IntegrationResult(source="", ok=True)
    with pytest.raises(ValueError, match="source is required"):
        IntegrationResult(source=" \t\n ", ok=True)


def test_result_defaults():
    result = IntegrationResult(source="MOCK_X", ok=True)

    assert result.data == {}
    assert result.reason is None


def test_result_is_immutable():
    result = IntegrationResult(source="MOCK_X", ok=True)

    with pytest.raises(FrozenInstanceError):
        result.ok = False


def test_source_constants():
    assert POLICYCENTER_SOURCE == "MOCK_POLICYCENTER"
    assert BILLINGCENTER_SOURCE == "MOCK_BILLINGCENTER"
    assert CLAIMCENTER_SOURCE == "MOCK_CLAIMCENTER"


def test_protocols_declare_expected_methods():
    assert all(
        hasattr(PolicyCenterService, method)
        for method in ("get_policy", "check_validity", "is_equipment_covered")
    )
    assert hasattr(BillingCenterService, "get_account_status")
    assert all(
        hasattr(ClaimCenterService, method)
        for method in ("register_claim", "get_status_history")
    )


def test_protocols_are_importable_without_database():
    source_path = Path(__file__).resolve().parents[1] / "app" / "integrations" / "base.py"
    source = source_path.read_text().lower()

    assert "sqlalchemy" not in source
    assert "fastapi" not in source