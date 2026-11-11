"""Media files on disk. Stored names are random; user input never forms a path."""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .db import Database, now_iso

STORED_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|webp|mp4|mov|webm)$")
Image.MAX_IMAGE_PIXELS = 80_000_000  # refuse decompression bombs


class MediaError(ValueError):
    pass


@dataclass(frozen=True)
class Detected:
    kind: str
    mime: str
    ext: str


def detect(data: bytes) -> Detected:
    head = data[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Detected("image", "image/png", "png")
    if head.startswith(b"\xff\xd8\xff"):
        return Detected("image", "image/jpeg", "jpg")
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return Detected("image", "image/webp", "webp")
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand == b"qt  ":
            return Detected("video", "video/quicktime", "mov")
        return Detected("video", "video/mp4", "mp4")
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return Detected("video", "video/webm", "webm")
    raise MediaError("unsupported file type (allowed: PNG, JPG, WEBP, MP4, MOV, WEBM)")


def clean_name(name: str, fallback: str) -> str:
    name = Path(name or "").name
    name = re.sub(r"[\x00-\x1f\x7f/\\]", "", name).strip()
    return (name or fallback)[:120]


class MediaStore:
    def __init__(self, db: Database, directory: Path):
        self.db = db
        self.directory = directory.resolve()
        (self.directory / "derived").mkdir(parents=True, exist_ok=True)

    def path(self, stored_name: str) -> Path:
        if not STORED_RE.match(stored_name):
            raise MediaError("invalid stored name")
        return self.directory / stored_name

    def save(self, *, user_id: int, data: bytes, original_name: str, source: str,
             job_id: int | None = None, prompt: str = "", width: int | None = None,
             height: int | None = None) -> dict:
        info = detect(data)
        if info.kind == "image":
            try:
                with Image.open(io.BytesIO(data)) as img:
                    img.verify()
                with Image.open(io.BytesIO(data)) as img:
                    width, height = img.size
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                raise MediaError("image file is corrupt or too large") from exc
        stored = f"{uuid.uuid4().hex}.{info.ext}"
        self.path(stored).write_bytes(data)
        media_id = self.db.execute(
            "INSERT INTO media (user_id, kind, stored_name, original_name, mime, size_bytes, width, height,"
            " source, job_id, prompt, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, info.kind, stored, clean_name(original_name, f"{info.kind}.{info.ext}"), info.mime,
             len(data), width, height, source, job_id, prompt[:2000], now_iso()),
        )
        return self.db.one("SELECT * FROM media WHERE id = ?", (media_id,))

    def delete(self, row: dict) -> None:
        for p in (self.path(row["stored_name"]), self.directory / "derived" / f"{row['stored_name']}.jpg"):
            p.unlink(missing_ok=True)

    def jpeg_path(self, row: dict) -> Path:
        """JPEG rendition of an image (Instagram only accepts JPEG)."""
        if row["kind"] != "image":
            raise MediaError("not an image")
        src = self.path(row["stored_name"])
        if row["mime"] == "image/jpeg":
            return src
        out = self.directory / "derived" / f"{row['stored_name']}.jpg"
        if not out.exists():
            with Image.open(src) as img:
                img.convert("RGB").save(out, "JPEG", quality=92)
        return out
