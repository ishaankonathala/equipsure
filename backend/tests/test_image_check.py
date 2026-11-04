from datetime import date, timedelta
from decimal import Decimal
import hashlib
import io
import secrets
import uuid

from PIL import Image, ImageDraw
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import (
    Business,
    Claim,
    ClaimDocument,
    ClaimEvent,
    Equipment,
    Policy,
    PolicyEquipment,
    User,
)
from app.models.enums import ClaimStatus, PolicyStatus
from app.services.document_storage import delete_document, write_document
from app.services.image_check import (
    BLUR_THRESHOLD,
    REVIEW_NOTE,
    blur_score,
    dhash,
    hamming,
)

PASSWORD = "test-image-password"


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def cleanup_docs():
    created_storage_names = []
    yield created_storage_names
    for name in created_storage_names:
        delete_document(name)


def _make_business(session, name: str = "Image Test Business") -> Business:
    biz = Business(id=uuid.uuid4(), name=name)
    session.add(biz)
    session.flush()
    return biz


def _make_user(session, email: str, role: str, business: Business | None = None) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(PASSWORD),
        full_name=f"User {role}",
        role=role,
        business_id=business.id if business else None,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _token_for(user: User) -> str:
    return create_access_token(
        user_id=str(user.id),
        role=user.role,
        business_id=str(user.business_id) if user.business_id else None,
    )


def _make_claim(session, business: Business, ref: str) -> Claim:
    today = date.today()
    policy = Policy(
        id=uuid.uuid4(),
        policy_number=f"EQP-{uuid.uuid4().hex[:8].upper()}",
        business_id=business.id,
        status=PolicyStatus.ACTIVE.value,
        start_date=today - timedelta(days=10),
        end_date=today + timedelta(days=350),
        premium_amount=Decimal("1000.00"),
        deductible_amount=Decimal("500.00"),
        coverage_limit=Decimal("50000.00"),
    )
    session.add(policy)
    session.flush()

    equipment = Equipment(
        id=uuid.uuid4(),
        business_id=business.id,
        category="REFRIGERATION",
        description="Cooler Unit",
    )
    session.add(equipment)
    session.flush()

    session.add(PolicyEquipment(policy_id=policy.id, equipment_id=equipment.id))
    session.flush()

    claim = Claim(
        id=uuid.uuid4(),
        reference=ref,
        business_id=business.id,
        policy_id=policy.id,
        equipment_id=equipment.id,
        status=ClaimStatus.SUBMITTED.value,
        incident_date=today - timedelta(days=2),
        incident_description="Compressor failure",
        amount_claimed=Decimal("1500.00"),
    )
    session.add(claim)
    session.flush()
    return claim


def _create_image_document(
    session,
    claim: Claim,
    image_bytes: bytes,
    filename: str = "photo.png",
    content_type: str = "image/png",
    cleanup_list: list[str] | None = None,
) -> ClaimDocument:
    sha = hashlib.sha256(image_bytes).hexdigest()
    storage_name = secrets.token_hex(32)
    write_document(storage_name, image_bytes)
    if cleanup_list is not None:
        cleanup_list.append(storage_name)

    doc = ClaimDocument(
        id=uuid.uuid4(),
        claim_id=claim.id,
        document_type="PHOTO",
        original_filename=filename,
        storage_name=storage_name,
        content_type=content_type,
        size_bytes=len(image_bytes),
        sha256=sha,
    )
    session.add(doc)
    session.flush()
    return doc


def _generate_pattern_image(size=(120, 120)) -> bytes:
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    for i in range(8):
        draw.rectangle(
            [i * 12, i * 10, i * 12 + 25, i * 10 + 30],
            fill=(i * 25, 255 - i * 25, (i * 35) % 256),
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _generate_blank_image(size=(10, 10)) -> bytes:
    img = Image.new("RGB", size, color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_dhash_and_blur_score_functions():
    img = Image.new("RGB", (100, 100), color=(0, 0, 0))
    dh = dhash(img)
    assert len(dh) == 16
    assert isinstance(dh, str)

    bs = blur_score(img)
    assert bs < BLUR_THRESHOLD
    assert bs == 0.0

    # Hamming distance
    assert hamming("0000000000000000", "0000000000000001") == 1
    assert hamming("0000000000000000", "0000000000000003") == 2
    assert hamming("ffffffffffffffff", "0000000000000000") == 64


def test_two_identical_images_on_two_claims_exact_copy_flag(
    session, client, cleanup_docs
):
    business = _make_business(session, "Exact Copy Biz")
    owner = _make_user(session, "exact.owner@example.com", "POLICYHOLDER", business)
    claim1 = _make_claim(session, business, "CLM-EXACT-001")
    claim2 = _make_claim(session, business, "CLM-EXACT-002")

    image_bytes = _generate_pattern_image(size=(120, 120))
    _create_image_document(session, claim1, image_bytes, cleanup_list=cleanup_docs)
    doc2 = _create_image_document(session, claim2, image_bytes, cleanup_list=cleanup_docs)

    headers = {"Authorization": f"Bearer {_token_for(owner)}"}

    # Query image flags for Claim 2
    res = client.get(f"/api/claims/{claim2.id}/image-flags", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["note"] == REVIEW_NOTE

    docs = data.get("documents", data.get("items"))
    assert len(docs) == 1
    entry = next(d for d in docs if d["document_id"] == str(doc2.id))
    assert "Exact copy used in another claim" in entry["flags"]


def test_resized_copy_visually_similar_flag(session, client, cleanup_docs):
    business = _make_business(session, "Similar Biz")
    owner = _make_user(session, "similar.owner@example.com", "POLICYHOLDER", business)
    claim1 = _make_claim(session, business, "CLM-SIM-001")
    claim2 = _make_claim(session, business, "CLM-SIM-002")

    # Claim 1 has 150x150 pattern image
    img1 = Image.new("RGB", (150, 150), "white")
    draw1 = ImageDraw.Draw(img1)
    for i in range(10):
        draw1.rectangle([i * 12, i * 10, i * 12 + 25, i * 10 + 30], fill=(i * 20, 200 - i * 15, i * 25))
    buf1 = io.BytesIO()
    img1.save(buf1, format="PNG")
    bytes1 = buf1.getvalue()
    _create_image_document(session, claim1, bytes1, filename="original.png", cleanup_list=cleanup_docs)

    # Claim 2 has resized 100x100 copy of the same pattern
    img2 = img1.resize((100, 100))
    buf2 = io.BytesIO()
    img2.save(buf2, format="PNG")
    bytes2 = buf2.getvalue()
    doc2 = _create_image_document(session, claim2, bytes2, filename="resized.png", cleanup_list=cleanup_docs)

    headers = {"Authorization": f"Bearer {_token_for(owner)}"}
    res = client.get(f"/api/claims/{claim2.id}/image-flags", headers=headers)
    assert res.status_code == 200
    data = res.json()

    docs = data.get("documents", data.get("items"))
    entry = next(d for d in docs if d["document_id"] == str(doc2.id))
    assert "Visually similar to a photo used in another claim" in entry["flags"]
    assert "Exact copy used in another claim" not in entry["flags"]


def test_tiny_blank_image_blur_flag(session, client, cleanup_docs):
    business = _make_business(session, "Blurry Biz")
    owner = _make_user(session, "blur.owner@example.com", "POLICYHOLDER", business)
    claim = _make_claim(session, business, "CLM-BLUR-001")

    blank_bytes = _generate_blank_image(size=(10, 10))
    doc = _create_image_document(session, claim, blank_bytes, filename="blank.png", cleanup_list=cleanup_docs)

    headers = {"Authorization": f"Bearer {_token_for(owner)}"}
    res = client.get(f"/api/claims/{claim.id}/image-flags", headers=headers)
    assert res.status_code == 200
    data = res.json()

    docs = data.get("documents", data.get("items"))
    entry = next(d for d in docs if d["document_id"] == str(doc.id))
    assert "Photo is very blurry" in entry["flags"]


def test_route_never_changes_status_and_never_writes_claim_events(
    session, client, cleanup_docs
):
    business = _make_business(session, "Audit Biz")
    owner = _make_user(session, "audit.owner@example.com", "POLICYHOLDER", business)
    claim = _make_claim(session, business, "CLM-AUDIT-001")
    image_bytes = _generate_blank_image()
    _create_image_document(session, claim, image_bytes, cleanup_list=cleanup_docs)

    initial_status = claim.status
    events_before = session.execute(select(func.count(ClaimEvent.id))).scalar()

    headers = {"Authorization": f"Bearer {_token_for(owner)}"}
    res = client.get(f"/api/claims/{claim.id}/image-flags", headers=headers)
    assert res.status_code == 200

    session.refresh(claim)
    assert claim.status == initial_status
    events_after = session.execute(select(func.count(ClaimEvent.id))).scalar()
    assert events_after == events_before
