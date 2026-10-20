import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Claim, ClaimDocument
from app.models.enums import ClaimStatus, DocumentType, UserRole
from app.models.user import User
from app.services.claims import get_claim_for_user
from app.services.checklist import checklist_status
from app.services.document_storage import delete_document, read_document, write_document
from app.services.documents import DocumentValidationError, validate_upload
from app.workflow.service import change_claim_status, sync_documents_status
from app.workflow.transitions import TransitionError

router = APIRouter()


def _can_upload(user: User, claim: Claim) -> bool:
    if user.role in {"OPS", "ADMIN"}:
        return True
    if user.role == "POLICYHOLDER":
        return claim.business_id == user.business_id
    return False


@router.get("/{claim_id}")
def read_claim(
    claim_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    claim = get_claim_for_user(db, claim_id, user)
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    return {
        "id": str(claim.id),
        "reference": claim.reference,
        "business_id": str(claim.business_id),
        "policy_id": str(claim.policy_id),
        "equipment_id": str(claim.equipment_id),
        "status": claim.status,
        "incident_date": claim.incident_date.isoformat(),
        "amount_claimed": str(claim.amount_claimed),
    }


@router.post("/{claim_id}/documents", status_code=status.HTTP_201_CREATED)
def upload_claim_document(
    claim_id: uuid.UUID,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    claim = get_claim_for_user(db, claim_id, user)
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    if not _can_upload(user, claim):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    allowed_types = {t.value for t in DocumentType}
    if document_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown document type",
        )

    buffer = bytearray()
    total = 0
    while True:
        chunk = file.file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds the size limit",
            )
        buffer.extend(chunk)

    try:
        validated = validate_upload(bytes(buffer), file.content_type)
    except DocumentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    original_filename = (file.filename or "upload").replace("\\", "/").split("/")[-1][:255]

    try:
        write_document(validated.storage_name, bytes(buffer))
        doc = ClaimDocument(
            id=uuid.uuid4(),
            claim_id=claim.id,
            document_type=document_type,
            original_filename=original_filename,
            storage_name=validated.storage_name,
            content_type=validated.content_type,
            size_bytes=validated.size_bytes,
            sha256=validated.sha256,
        )
        db.add(doc)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        delete_document(validated.storage_name)
        raise

    present = set(
        db.execute(
            select(ClaimDocument.document_type).where(ClaimDocument.claim_id == claim.id)
        ).scalars().all()
    )
    try:
        sync_documents_status(db, claim, present)
        db.commit()
    except (TransitionError, ValueError):
        db.rollback()

    return {
        "id": str(doc.id),
        "claim_id": str(claim.id),
        "document_type": doc.document_type,
        "original_filename": doc.original_filename,
        "content_type": doc.content_type,
        "size_bytes": doc.size_bytes,
        "sha256": doc.sha256,
    }


@router.get("/{claim_id}/documents/{document_id}")
def read_claim_document(
    claim_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    claim = get_claim_for_user(db, claim_id, user)
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    doc = db.execute(
        select(ClaimDocument).where(
            ClaimDocument.id == document_id,
            ClaimDocument.claim_id == claim.id,
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        data = read_document(doc.storage_name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found",
        ) from exc

    safe_name = doc.original_filename.replace('"', "")
    return Response(
        content=data,
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{claim_id}/checklist")
def read_claim_checklist(
    claim_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    claim = get_claim_for_user(db, claim_id, user)
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    present = db.execute(
        select(ClaimDocument.document_type).where(ClaimDocument.claim_id == claim.id)
    ).scalars().all()
    return checklist_status(present)


class StatusChangeRequest(BaseModel):
    target_status: str
    explanation: str


@router.post("/{claim_id}/status")
def change_claim_status_route(
    claim_id: uuid.UUID,
    body: StatusChangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    claim = get_claim_for_user(db, claim_id, user)
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    try:
        target = ClaimStatus(body.target_status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown claim status",
        ) from exc

    try:
        role = UserRole(user.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted",
        ) from exc

    if role == UserRole.POLICYHOLDER and claim.business_id != user.business_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    try:
        event = change_claim_status(db, claim, target, role, user.id, body.explanation)
        db.commit()
    except TransitionError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception:
        db.rollback()
        raise

    return {
        "claim_id": str(claim.id),
        "old_status": event.old_status,
        "new_status": event.new_status,
        "source": event.source,
    }