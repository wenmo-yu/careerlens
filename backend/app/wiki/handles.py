"""Invocation-local short-handle table for Wiki citation mapping.

Adapted from WeKnora's modelcontext.HandleTable (wiki_ingest_cite.go:179,
NewHandleTable("c", 3, 0)). Models receive short handles like ``c000`` instead
of long UUIDs: fewer tokens, and far less opportunity to fabricate an ID. Before
anything reaches application state, handles are resolved back to stable
evidence_ids; unknown handles are dropped, never trusted.
"""

import re

HANDLE_PATTERN = re.compile(r"^c\d{3,}$")


class HandleTable:
    def __init__(self, prefix: str = "c", width: int = 3, start: int = 0) -> None:
        self._prefix = prefix
        self._width = width
        self._next = start
        self._by_handle: dict[str, str] = {}
        self._by_id: dict[str, str] = {}
        self._unknown: list[str] = []

    def register(self, stable_id: str) -> str:
        """Register a stable id and return its short handle (idempotent)."""
        if stable_id in self._by_id:
            return self._by_id[stable_id]
        handle = f"{self._prefix}{self._next:0{self._width}d}"
        self._next += 1
        self._by_handle[handle] = stable_id
        self._by_id[stable_id] = handle
        return handle

    def handle(self, stable_id: str) -> str | None:
        return self._by_id.get(stable_id)

    def resolve(self, handle: str) -> str | None:
        """Translate a handle to its stable id; record unknown handles."""
        stable = self._by_handle.get(handle)
        if stable is None:
            self._unknown.append(handle)
        return stable

    @property
    def unknown_handles(self) -> list[str]:
        return list(self._unknown)

    def render_block(self, handle: str, index: int, content: str) -> str:
        return f'<c id="{handle}" index="{index}">{content}</c>'

    def strip_inline_citations(self, markdown: str) -> str:
        """Remove inline ``[c000, c001]`` markers from final page content.

        Mirrors WeKnora's wikiInlineChunkCitationRegex (wiki_page.go:25-41):
        stable references live in chunk_refs, not in the rendered Markdown.
        """
        return re.sub(r"[ \t]*\[c\d{3,}(?:[,;]\s*c\d{3,})*\]", "", markdown).strip()

    def __len__(self) -> int:
        return len(self._by_handle)
