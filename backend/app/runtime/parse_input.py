import json
import sys
from contextlib import redirect_stdout
from dataclasses import asdict

from app.ingestion.contract import ParsedDocument
from app.ingestion.files import parse_document
from app.ingestion.media import get_media_extractor, parse_media


def parse_upload(operation: str, filename: str, data: bytes) -> ParsedDocument:
    if operation == "media_import":
        parsed = parse_media(get_media_extractor(), filename, data)
    else:
        parsed = parse_document(filename, data)
    if len(parsed.blocks) > 2000 or sum(len(block.content) for block in parsed.blocks) > 1_000_000:
        raise ValueError("Parsed document exceeds the background processing limit")
    return parsed


def main() -> None:
    try:
        operation, filename = json.loads(sys.stdin.buffer.readline())
        data = sys.stdin.buffer.read()
        with redirect_stdout(sys.stderr):
            parsed = parse_upload(operation, filename, data)
        result = {"document": asdict(parsed)}
    except RuntimeError:
        result = {"error": "parser_unavailable"}
    except Exception:
        result = {"error": "invalid_upload"}
    sys.stdout.buffer.write(b"\n" + json.dumps(result, ensure_ascii=True).encode("utf-8") + b"\n")


if __name__ == "__main__":
    main()
