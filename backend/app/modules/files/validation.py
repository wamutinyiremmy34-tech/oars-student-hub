"""Upload validation. The file's CONTENT decides its type; the client's name and MIME type are ignored.

Allow-list only: anything that is not positively identified as one of these formats is rejected,
which excludes executables, scripts, HTML/SVG, archives and legacy (macro-capable) Office files.
"""

import codecs
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO


@dataclass(frozen=True)
class FileKind:
    ext: str
    mime: str


PDF = FileKind("pdf", "application/pdf")
DOCX = FileKind("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
PPTX = FileKind("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation")
XLSX = FileKind("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
PNG = FileKind("png", "image/png")
JPEG = FileKind("jpg", "image/jpeg")
TEXT = FileKind("txt", "text/plain")

_MAX_ZIP_ENTRIES = 10_000
_TEXT_PROBE_BYTES = 64 * 1024


def _sniff_ooxml(stream: BinaryIO) -> FileKind | None:
    """Identify an Office Open XML file from the zip directory only (nothing is decompressed)."""
    try:
        with zipfile.ZipFile(stream) as archive:
            names = archive.namelist()
    except (zipfile.BadZipFile, OSError, ValueError):
        return None
    if len(names) > _MAX_ZIP_ENTRIES or "[Content_Types].xml" not in names:
        return None
    lowered = {n.lower() for n in names}
    if any(n.endswith("vbaproject.bin") for n in lowered):  # macros
        return None
    if "word/document.xml" in lowered:
        return DOCX
    if "ppt/presentation.xml" in lowered:
        return PPTX
    if "xl/workbook.xml" in lowered:
        return XLSX
    return None


def _looks_like_text(head: bytes) -> bool:
    if not head or b"\x00" in head:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
    except UnicodeDecodeError:
        return False
    return True


def sniff(stream: BinaryIO) -> FileKind | None:
    """Return the detected kind, or None if the content is not an allowed type."""
    stream.seek(0)
    head = stream.read(_TEXT_PROBE_BYTES)
    stream.seek(0)
    if head.startswith(b"%PDF-"):
        return PDF
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"PK\x03\x04"):
        kind = _sniff_ooxml(stream)
        stream.seek(0)
        return kind
    if head.startswith((b"MZ", b"\x7fELF", b"#!")):
        return None
    if (
        head.lstrip()[:1] == b"<"
    ):  # HTML, SVG and XML can carry scripts: never accept them as "text"
        return None
    return TEXT if _looks_like_text(head) else None


def secure_display_name(original: str | None, kind: FileKind) -> str:
    """A safe name to show and offer as the download name. The extension always comes from the sniffed kind."""
    name = PurePosixPath((original or "").replace("\\", "/")).name
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = unicodedata.normalize("NFKC", stem)
    stem = re.sub(r"[^A-Za-z0-9 _-]+", "", stem).strip(" ._-")[:80]
    return f"{stem or 'document'}.{kind.ext}"
