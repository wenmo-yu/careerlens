import pytest

from app.ingestion.chunking import chunk_text, normalize_text


def test_normalize_text_removes_noise():
    assert normalize_text(" A\t B\r\n\r\n\r\nC\x00 ") == "A B\n\nC"


def test_chunk_text_keeps_overlap_and_content():
    chunks = chunk_text("第一段。" * 100, chunk_size=100, overlap=10)
    assert len(chunks) > 1
    assert all(chunks)


def test_chunk_size_must_exceed_overlap():
    with pytest.raises(ValueError):
        chunk_text("content", chunk_size=10, overlap=10)

