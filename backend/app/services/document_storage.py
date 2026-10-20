import re
from pathlib import Path

from app.core.config import settings


def resolve_storage_root() -> Path:
    root = Path(settings.storage_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validated_path(storage_name: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", storage_name):
        raise ValueError("storage_name must be exactly 64 lowercase hex characters")
    return resolve_storage_root() / storage_name


def write_document(storage_name: str, data: bytes) -> None:
    path = _validated_path(storage_name)
    with open(path, "xb") as handle:
        handle.write(data)


def read_document(storage_name: str) -> bytes:
    path = _validated_path(storage_name)
    return path.read_bytes()


def delete_document(storage_name: str) -> None:
    path = _validated_path(storage_name)
    path.unlink(missing_ok=True)
