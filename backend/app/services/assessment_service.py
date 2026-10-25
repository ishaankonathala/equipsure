from app.ai.provider import AIProvider, AIProviderError
from app.models import Claim
from app.services.assessment import AssessmentError, ClaimAssessment, request_assessment


def run_claim_assessment(
    provider: AIProvider,
    claim: Claim,
    document_types: list[str],
) -> ClaimAssessment:
    return request_assessment(
        provider,
        claim_reference=claim.reference,
        incident_date=claim.incident_date.isoformat(),
        incident_description=claim.incident_description,
        amount_claimed=str(claim.amount_claimed),
        document_types=document_types,
    )