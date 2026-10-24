"""Simulated service interfaces; no real Guidewire API is used."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol
import uuid


@dataclass(frozen=True)
class IntegrationResult:
    source: str
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source is required")


POLICYCENTER_SOURCE = "MOCK_POLICYCENTER"
BILLINGCENTER_SOURCE = "MOCK_BILLINGCENTER"
CLAIMCENTER_SOURCE = "MOCK_CLAIMCENTER"


class PolicyCenterService(Protocol):
    source: str

    def get_policy(self, policy_number: str) -> IntegrationResult: ...

    def check_validity(self, policy_number: str, on_date: date) -> IntegrationResult: ...

    def is_equipment_covered(
        self, policy_number: str, equipment_id: uuid.UUID
    ) -> IntegrationResult: ...


class BillingCenterService(Protocol):
    source: str

    def get_account_status(
        self, policy_number: str, on_date: date
    ) -> IntegrationResult: ...


class ClaimCenterService(Protocol):
    source: str

    def register_claim(self, reference: str) -> IntegrationResult: ...

    def get_status_history(self, claim_id: uuid.UUID) -> IntegrationResult: ...