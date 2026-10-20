from app.models.enums import ClaimStatus, UserRole


class TransitionError(Exception):
    """Raised when a claim status transition is not permitted."""


ALLOWED_TRANSITIONS: dict[ClaimStatus, frozenset[ClaimStatus]] = {
    ClaimStatus.SUBMITTED: frozenset(
        {ClaimStatus.UNDER_VERIFICATION, ClaimStatus.WITHDRAWN}
    ),
    ClaimStatus.UNDER_VERIFICATION: frozenset(
        {
            ClaimStatus.DOCUMENTS_REQUIRED,
            ClaimStatus.UNDER_REVIEW,
            ClaimStatus.WITHDRAWN,
        }
    ),
    ClaimStatus.DOCUMENTS_REQUIRED: frozenset(
        {ClaimStatus.UNDER_VERIFICATION, ClaimStatus.WITHDRAWN}
    ),
    ClaimStatus.UNDER_REVIEW: frozenset(
        {
            ClaimStatus.INVESTIGATION_ASSIGNED,
            ClaimStatus.DECISION_PENDING,
            ClaimStatus.WITHDRAWN,
        }
    ),
    ClaimStatus.INVESTIGATION_ASSIGNED: frozenset(
        {ClaimStatus.DECISION_PENDING, ClaimStatus.WITHDRAWN}
    ),
    ClaimStatus.DECISION_PENDING: frozenset(
        {ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.WITHDRAWN}
    ),
    ClaimStatus.APPROVED: frozenset({ClaimStatus.SETTLEMENT_IN_PROGRESS}),
    ClaimStatus.REJECTED: frozenset({ClaimStatus.CLOSED}),
    ClaimStatus.SETTLEMENT_IN_PROGRESS: frozenset({ClaimStatus.SETTLED}),
    ClaimStatus.SETTLED: frozenset({ClaimStatus.CLOSED}),
    ClaimStatus.CLOSED: frozenset(),
    ClaimStatus.WITHDRAWN: frozenset(),
}

OPEN_STATUSES: frozenset[ClaimStatus] = frozenset(
    status
    for status, targets in ALLOWED_TRANSITIONS.items()
    if ClaimStatus.WITHDRAWN in targets
)

POLICYHOLDER_ACTIONS: frozenset[ClaimStatus] = frozenset(
    {ClaimStatus.WITHDRAWN}
)


def can_transition(current: ClaimStatus, target: ClaimStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def check_transition(
    current: ClaimStatus, target: ClaimStatus, actor_role: UserRole
) -> None:
    if not can_transition(current, target):
        raise TransitionError(
            f"Cannot move claim from {current.value} to {target.value}"
        )
    if (
        actor_role == UserRole.POLICYHOLDER
        and target not in POLICYHOLDER_ACTIONS
    ):
        raise TransitionError("Policyholders may only withdraw a claim")
