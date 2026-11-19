"""Table row-identity guard for Wiki writes.

WeKnora's wiki_page.go:143-227 caught a real production failure: an agent
rewriting a whole page would silently drop rows from a 100-row table down to
30, returning finish_reason=stop with no error. Because a no-op-looking write
does not bump version, callers could not tell the write had lost data. The guard
compares table-row identity before accepting a rewrite and rejects excessive
loss instead of silently persisting it.
"""

import re
from collections import Counter

# A Markdown table row: a line starting and ending with a pipe.
_ROW_LINE = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def table_row_identities(markdown: str) -> list[str]:
    """Extract ordered row identities (first cell of each *data* row).

    Markdown tables are a header row, a separator row, then data rows. We walk
    consecutive pipe-line blocks and skip the first two lines of each block so
    the header is never mistaken for data; the identity is the leading cell,
    stable across cosmetic reformatting of other columns.
    """
    identities: list[str] = []
    block: list[str] = []

    def flush() -> None:
        if len(block) < 2 or not _SEPARATOR.match(block[1]):
            return
        # Skip header + separator (first two lines); only data rows remain.
        for line in block[2:]:
            cells = re.split(r"(?<!\\)\|", line.strip()[1:-1])
            identity = cells[0].strip()
            if not identity:
                identity = " | ".join(cell.strip() for cell in cells)
            identities.append(identity)

    for line in markdown.splitlines():
        if _ROW_LINE.match(line):
            block.append(line)
        else:
            flush()
            block = []
    flush()
    return identities


def row_identity_loss_ratio(original: str, rewritten: str) -> float:
    """Fraction of original table-row identities missing from the rewrite."""
    original_ids = table_row_identities(original)
    if not original_ids:
        return 0.0
    rewritten_counts = Counter(table_row_identities(rewritten))
    missing = sum((Counter(original_ids) - rewritten_counts).values())
    return missing / len(original_ids)


class DroppedTableRowsError(Exception):
    """A rewrite lost too many table rows and was rejected."""


def assert_rows_preserved(
    original: str,
    rewritten: str,
    *,
    max_loss_ratio: float = 0.0,
    source_tables: list[str] | None = None,
) -> None:
    """Reject a rewrite that dropped table rows beyond the tolerance.

    ``source_tables`` lets a compiler check each original source table against
    the rewritten page (WeKnora checks all tables on the page). When omitted,
    the original page content is used.
    """
    sources = source_tables if source_tables is not None else [original]
    loss = row_identity_loss_ratio("\n\n".join(sources), rewritten)
    if loss > max_loss_ratio:
        raise DroppedTableRowsError(
            f"rewrite dropped {loss:.0%} of table rows (limit {max_loss_ratio:.0%})"
        )
