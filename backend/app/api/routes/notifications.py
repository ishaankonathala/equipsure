import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Notification, User
from app.services.messaging import list_notifications, mark_read

router = APIRouter()


def _notification_payload(notification: Notification) -> dict:
    return {
        "id": str(notification.id),
        "user_id": str(notification.user_id),
        "claim_id": str(notification.claim_id) if notification.claim_id else None,
        "kind": notification.kind,
        "message": notification.message,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat(),
    }


@router.get("")
def read_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        _notification_payload(notification)
        for notification in list_notifications(db, user)
    ]


@router.patch("/{notification_id}/read")
def read_notification(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    try:
        notification = mark_read(db, notification, user)
        db.commit()
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        ) from exc
    except Exception:
        db.rollback()
        raise

    return _notification_payload(notification)