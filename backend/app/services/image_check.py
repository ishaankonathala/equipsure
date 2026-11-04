import io
from typing import Any
import uuid

from PIL import Image, ImageFilter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, ClaimDocument, ImageFingerprint
from app.services.document_storage import read_document

# Demo value: photos with edge variance below this threshold are considered very blurry.
BLUR_THRESHOLD: float = 50.0
REVIEW_NOTE: str = "Flags are for officer review. They are not decisions."


def dhash(image: Image.Image) -> str:
    """Compute 64-bit difference hash (dHash) as a 16-character hex string.

    1. Convert image to grayscale.
    2. Resize to 9 columns x 8 rows.
    3. Compare adjacent horizontal pixels (left > right).
    4. Pack 64 boolean comparisons into a 16 hex character string.
    """
    grayscale = image.convert("L")
    resized = grayscale.resize((9, 8), Image.Resampling.LANCZOS)
    if hasattr(resized, "get_flattened_data"):
        pixels = list(resized.get_flattened_data())
    else:
        pixels = list(resized.getdata())

    diff: list[int] = []
    for row in range(8):
        for col in range(8):
            left = pixels[row * 9 + col]
            right = pixels[row * 9 + col + 1]
            diff.append(1 if left > right else 0)

    decimal_val = 0
    for bit in diff:
        decimal_val = (decimal_val << 1) | bit
    return f"{decimal_val:016x}"


def hamming(a: str, b: str) -> int:
    """Compute Hamming distance (differing bits) between two hex hashes."""
    return (int(a, 16) ^ int(b, 16)).bit_count()


def blur_score(image: Image.Image) -> float:
    """Compute blur score: variance of an edge-filtered grayscale image.

    Converts to grayscale, applies FIND_EDGES filter, and calculates variance
    of the resulting edge pixel values.
    """
    grayscale = image.convert("L")
    edges = grayscale.filter(ImageFilter.FIND_EDGES)
    if hasattr(edges, "get_flattened_data"):
        pixels = list(edges.get_flattened_data())
    else:
        pixels = list(edges.getdata())

    if not pixels:
        return 0.0

    mean = sum(pixels) / len(pixels)
    variance = sum((x - mean) ** 2 for x in pixels) / len(pixels)
    return float(variance)


def get_or_create_fingerprint(
    session: Session, doc: ClaimDocument
) -> ImageFingerprint | None:
    """Ensure fingerprint exists for an image document (idempotent)."""
    if doc.content_type not in ("image/jpeg", "image/png"):
        return None

    fp = session.execute(
        select(ImageFingerprint).where(ImageFingerprint.document_id == doc.id)
    ).scalar_one_or_none()
    if fp is not None:
        return fp

    raw_bytes = read_document(doc.storage_name)
    with Image.open(io.BytesIO(raw_bytes)) as img:
        width, height = img.size
        dh = dhash(img)
        bs = blur_score(img)

    fp = ImageFingerprint(
        id=uuid.uuid4(),
        document_id=doc.id,
        sha256=doc.sha256,
        dhash=dh,
        blur_score=bs,
        width=width,
        height=height,
    )
    session.add(fp)
    session.flush()
    return fp


def analyze_claim_image_flags(
    session: Session, claim: Claim
) -> dict[str, Any]:
    """Analyse all documents for a claim and return flags for officer review."""
    documents = session.execute(
        select(ClaimDocument)
        .where(ClaimDocument.claim_id == claim.id)
        .order_by(ClaimDocument.created_at.asc(), ClaimDocument.id.asc())
    ).scalars().all()

    # Get fingerprints/documents for all other claims to compare against
    other_documents = session.execute(
        select(ClaimDocument).where(ClaimDocument.claim_id != claim.id)
    ).scalars().all()
    other_sha256_set = {d.sha256 for d in other_documents}

    # Ensure other documents have fingerprints where applicable
    for other_doc in other_documents:
        if other_doc.content_type in ("image/jpeg", "image/png"):
            get_or_create_fingerprint(session, other_doc)

    other_fingerprints = session.execute(
        select(ImageFingerprint)
        .join(ClaimDocument, ClaimDocument.id == ImageFingerprint.document_id)
        .where(ClaimDocument.claim_id != claim.id)
    ).scalars().all()

    doc_results: list[dict[str, Any]] = []

    for doc in documents:
        if doc.content_type == "application/pdf":
            doc_results.append(
                {
                    "document_id": str(doc.id),
                    "original_filename": doc.original_filename,
                    "flags": [],
                    "note": "PDF document skipped from image analysis",
                }
            )
            continue

        if doc.content_type not in ("image/jpeg", "image/png"):
            doc_results.append(
                {
                    "document_id": str(doc.id),
                    "original_filename": doc.original_filename,
                    "flags": [],
                    "note": f"Skipped: unsupported content type {doc.content_type}",
                }
            )
            continue

        fp = get_or_create_fingerprint(session, doc)
        flags: list[str] = []

        if doc.sha256 in other_sha256_set:
            flags.append("Exact copy used in another claim")

        is_similar = False
        for other_fp in other_fingerprints:
            if hamming(fp.dhash, other_fp.dhash) <= 5:
                if other_fp.sha256 != fp.sha256 or "Exact copy used in another claim" not in flags:
                    is_similar = True
                    break
        if is_similar:
            flags.append("Visually similar to a photo used in another claim")

        if fp.blur_score < BLUR_THRESHOLD:
            flags.append("Photo is very blurry")

        doc_results.append(
            {
                "document_id": str(doc.id),
                "original_filename": doc.original_filename,
                "flags": flags,
            }
        )

    return {
        "claim_id": str(claim.id),
        "documents": doc_results,
        "items": doc_results,
        "note": REVIEW_NOTE,
    }

