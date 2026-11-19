"""Structure-aware parsing contract shared across all ingestion formats.

Every parser (PDF / DOCX / table / OCR / ASR / plain text) produces a
:class:`ParsedDocument` made of :class:`ParsedBlock` values. Phase one persists
these blocks; phase two's Wiki references and phase three's event sourcing
anchor on ``evidence_id``. Defining the contract here first — before any parser
is upgraded — is deliberate: an inconsistent contract would force a rewrite of
both later phases.

Field semantics mirror WeKnora's source_blocks (start/end/locator):
- ``evidence_id`` is stable for the block's lifetime (never regenerated).
- ``content_hash`` is sha256 of the normalized content and, together with
  ``user_id``, is the evidence-level dedup key.
- location fields (page/bbox/time/section) let a citation return the reader to
  the exact origin of a multi-format upload.
"""

import hashlib
import uuid
from dataclasses import dataclass, field


def content_fingerprint(text: str) -> str:
    """Stable sha256 over normalized text — the evidence dedup key source."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def source_fingerprint(raw: bytes) -> str:
    """File-level identity for idempotent re-uploads."""
    return hashlib.sha256(raw).hexdigest()


def new_evidence_id() -> str:
    return str(uuid.uuid4())


@dataclass
class ParsedBlock:
    content: str
    block_type: str = "text"
    block_index: int = 0
    evidence_id: str = field(default_factory=new_evidence_id)
    char_start: int = 0
    char_end: int = 0
    page_no: int | None = None
    bbox: dict | list[float] | None = None
    time_start: float | None = None
    time_end: float | None = None
    section_path: str | None = None
    image_ref: str | None = None
    source_type: str = "text"
    content_revision: int = 1
    source_metadata: dict = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return content_fingerprint(self.content)


@dataclass
class ParsedDocument:
    doc_id: str
    blocks: list[ParsedBlock]
    source_type: str
    metadata: dict = field(default_factory=dict)
    parse_status: str = "parsed"

    @property
    def source_hash(self) -> str:
        """Concatenated-block fingerprint, used when no raw bytes are retained."""
        digest = hashlib.sha256()
        for block in self.blocks:
            digest.update(block.content_hash.encode("ascii"))
        return digest.hexdigest()

    @property
    def markdown(self) -> str:
        parts: list[str] = []
        for block in sorted(self.blocks, key=lambda b: b.block_index):
            if block.block_type == "table":
                parts.append(block.content)
            else:
                parts.append(block.content)
        return "\n\n".join(parts)
