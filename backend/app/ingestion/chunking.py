import re


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        hard_end = min(start + chunk_size, len(normalized))
        end = hard_end
        if hard_end < len(normalized):
            candidates = [
                normalized.rfind(separator, start + chunk_size // 2, hard_end)
                for separator in ("\n\n", "\n", "。", "！", "？", ". ")
            ]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + 1

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)

    return chunks

