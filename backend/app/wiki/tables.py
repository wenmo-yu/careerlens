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

_SEPARATOR = re.compile(r":?-+:?")
_FENCE = re.compile(r"^ {0,3}(\x60{3,}|~{3,})")
_HEADING = re.compile(r"^ {0,3}#{1,6}\s+(.*)$")
_EMPHASIS = str.maketrans("", "", "*_`")


def _normalize_cell(cell: str) -> str:
    """Normalise a cell so cosmetic edits read as the same identity.

    Port of WeKnora's ``normalizeWikiWriteCell`` (wiki_write_row_guard.go:53):
    full-width spaces become ordinary spaces, emphasis/code markers are
    dropped, whitespace runs collapse, and the result is lower-cased. Formatting
    and case are exactly what a model changes freely while re-emitting a page,
    so neither may register as a lost row.
    """
    cell = cell.replace("\u3000", " ").translate(_EMPHASIS)
    return " ".join(cell.split()).casefold()


def _cells(line: str) -> list[str]:
    """Split delimiters while retaining escaped and inline-code pipes."""
    line = line.strip()
    cells: list[str] = []
    current: list[str] = []
    code_delimiter = 0
    index = 0
    ended_on_separator = False
    while index < len(line):
        char = line[index]
        ended_on_separator = False
        if char == "\\" and index + 1 < len(line) and line[index + 1] in {"|", "\\"}:
            index += 1
            current.append(line[index])
        elif char == "\x60":
            start = index
            while index + 1 < len(line) and line[index + 1] == "\x60":
                index += 1
            length = index - start + 1
            if not code_delimiter:
                code_delimiter = length
            elif code_delimiter == length:
                code_delimiter = 0
        elif char == "|" and not code_delimiter:
            cells.append("".join(current))
            current = []
            ended_on_separator = True
        else:
            current.append(char)
        index += 1
    if not cells:
        return []
    if not ended_on_separator:
        cells.append("".join(current))
    return cells[1:] if line.startswith("|") else cells


def _unfenced_lines(markdown: str):
    fence = ""
    for line in markdown.splitlines():
        match = _FENCE.match(line)
        marker = match[1] if match else ""
        if fence:
            if marker.startswith(fence) and not line.strip().strip(fence[0]).strip():
                fence = ""
        elif marker:
            fence = marker
            yield ""
        else:
            yield line


def _row_keys(markdown: str, *, include_heading: bool):
    heading = ""
    header: list[str] = []
    active_header: tuple[str, ...] = ()
    for line in _unfenced_lines(markdown):
        match = _HEADING.match(line)
        if match:
            heading = _normalize_cell(match[1])
        cells = _cells(line)
        separator = bool(cells) and all(_SEPARATOR.fullmatch(cell.strip()) for cell in cells)
        if not cells:
            active_header = ()
        elif separator and len(header) == len(cells):
            active_header = tuple(_normalize_cell(cell) for cell in header)
        elif active_header:
            row = tuple(_normalize_cell(cell) for cell in cells)
            # A leading/trailing blank introduced by formatting is harmless.
            # Blanks between data cells still carry column position.
            first = next((index for index, cell in enumerate(row) if cell), len(row))
            last = next((index for index, cell in enumerate(reversed(row)) if cell), len(row))
            if first < len(row):
                yield (heading if include_heading else "", active_header, row[first:len(row)-last])
        header = cells


def table_row_identities(markdown: str) -> list[str]:
    """Return the first populated cell of each data row for callers and tutorials."""
    return [row[0] for _, _, row in _row_keys(markdown, include_heading=False)]


def row_identity_loss_ratio(
    original: str, rewritten: str, *, include_heading: bool = True,
) -> float:
    """Fraction of original table-row identities missing from the rewrite.

    Cell identities are normalized by ``_normalize_cell`` (WeKnora's rule), but
    the ratio intentionally uses a multiset denominator rather than WeKnora's
    distinct-identity count: dropping one of two identical rows is a real data
    loss and must not be diluted by the duplicate. This keeps the guard a
    stricter safety net than the upstream variant.
    """
    original_ids = list(_row_keys(original, include_heading=include_heading))
    if not original_ids:
        return 0.0
    rewritten_counts = Counter(_row_keys(rewritten, include_heading=include_heading))
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
    loss = row_identity_loss_ratio(
        "\n\n".join(sources), rewritten, include_heading=source_tables is None,
    )
    if loss > max_loss_ratio:
        raise DroppedTableRowsError(
            f"rewrite dropped {loss:.0%} of table rows (limit {max_loss_ratio:.0%})"
        )
