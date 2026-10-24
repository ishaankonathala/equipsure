import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.base import CLAIMCENTER_SOURCE, IntegrationResult
from app.models import Claim, ClaimEvent


class MockClaimCenter:
    source = CLAIMCENTER_SOURCE

    def __init__(self, session: Session) -> None:
        self.session = session

    def register_claim(self, reference: str) -> IntegrationResult:
        normalized_reference = reference.strip()
        if not normalized_reference:
            return IntegrationResult(
                source=self.source,
                ok=False,
                reason="Claim reference is required",
            )

        claim = self.session.execute(
            select(Claim).where(Claim.reference == normalized_reference)
        ).scalar_one_or_none()
        if claim is not None:
            return IntegrationResult(
                source=self.source,
                ok=False,
                reason="Claim reference already exists",
            )

        return IntegrationResult(
            source=self.source,
            ok=True,
            data={"reference": normalized_reference},
        )

    def get_status_history(self, claim_id: uuid.UUID) -> IntegrationResult:
        claim = self.session.execute(
            select(Claim).where(Claim.id == claim_id)
        ).scalar_one_or_none()
        if claim is None:
            return IntegrationResult(
                source=self.source,
                ok=False,
                reason="Claim not found",
            )

        events = self.session.execute(
            select(ClaimEvent)
            .where(ClaimEvent.claim_id == claim.id)
            .order_by(ClaimEvent.id.asc())
        ).scalars().all()

        return IntegrationResult(
            source=self.source,
            ok=True,
            data={
                "claim_id": str(claim_id),
                "events": [
                    {
                        "old_status": event.old_status,
                        "new_status": event.new_status,
                        "source": event.source,
                        "explanation": event.explanation,
                        "created_at": event.created_at.isoformat(),
                    }
                    for event in events
                ],
            },
        )