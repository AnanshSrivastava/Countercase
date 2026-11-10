"""Seller uploads: validated, stored under server-generated names, never trusted as proof.

- The file type comes from the file's magic bytes, not its name or declared content type.
- Only png, jpg and pdf are accepted (no SVG/HTML: those would be script-capable on our origin).
- The size cap is enforced when the handler reads the file. FastAPI has already parsed the
  multipart body by then, so this is not a defence against huge requests: a real request-size
  limit belongs at the reverse proxy in front of the API.
"""

import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.settings import settings

MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"%PDF-", "pdf"),
)
CONTENT_TYPES = {"png": "image/png", "jpg": "image/jpeg", "pdf": "application/pdf"}
FILE_NAME = re.compile(r"^[0-9a-f]{32}\.(png|jpg|pdf)$")
CHUNK = 64 * 1024


class UploadError(Exception):
    def __init__(self, status_code: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code, self.error, self.detail = status_code, error, detail


async def read_limited(file: UploadFile, limit: int | None = None) -> bytes:
    limit = limit or settings.max_upload_bytes
    data = bytearray()
    while chunk := await file.read(CHUNK):
        data.extend(chunk)
        if len(data) > limit:
            raise UploadError(413, "file_too_large", f"file exceeds {limit // (1024 * 1024)} MB")
    if not data:
        raise UploadError(422, "empty_file", "the uploaded file is empty")
    return bytes(data)


def sniff_extension(data: bytes) -> str:
    for prefix, ext in MAGIC:
        if data.startswith(prefix):
            return ext
    raise UploadError(415, "unsupported_file_type", "only PNG, JPG and PDF files are accepted")


def store(data: bytes, ext: str) -> str:
    name = f"{uuid.uuid4().hex}.{ext}"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / name).write_bytes(data)
    return name


def path_for(name: str) -> Path | None:
    """Resolve a stored file by name; None unless the name is exactly one we generated."""
    if not FILE_NAME.fullmatch(name):
        return None
    path = settings.upload_dir / name
    return path if path.is_file() else None


def display_name(raw: str | None) -> str:
    """Original file name for the evidence summary: basename only, printable, short."""
    base = (raw or "file").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(c for c in base if c.isprintable()).strip()
    return cleaned[:80] or "file"
