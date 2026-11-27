from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from app.core.config import get_settings
from app.ingestion.contract import ParsedBlock, ParsedDocument

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
AUDIO_VIDEO_SUFFIXES = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".webm", ".mkv"}
_IMAGE_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".bmp": "BMP"}
_CONTAINER_FORMATS = {
    ".mp3": "mp3", ".wav": "wav", ".m4a": "m4a", ".mp4": "mp4",
    ".mov": "mov", ".webm": "webm", ".mkv": "matroska",
}


class MediaExtractor(Protocol):
    def extract(self, filename: str, content: bytes) -> tuple[str, dict[str, Any]]: ...

    def extract_blocks(self, filename: str, content: bytes) -> list[dict[str, Any]]:
        """Structured view with locations (bbox for OCR, time range for ASR).

        Default implementation degrades to a single untimed block so custom
        extractors (e.g. test fakes) remain compatible.
        """
        text, metadata = self.extract(filename, content)
        return [
            {
                "content": text,
                "block_type": "text",
                "source_type": "media",
                "source_metadata": metadata,
            }
        ]


class OptionalMultimodalExtractor:
    def extract(self, filename: str, content: bytes) -> tuple[str, dict[str, Any]]:
        suffix = Path(filename).suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            return self._ocr_image(content, suffix)
        if suffix in AUDIO_VIDEO_SUFFIXES:
            return self._transcribe(filename, content)
        raise ValueError(f"Unsupported media type: {suffix or 'unknown'}")

    def extract_blocks(self, filename: str, content: bytes) -> list[dict[str, Any]]:
        suffix = Path(filename).suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            return self._ocr_blocks(content, suffix)
        if suffix in AUDIO_VIDEO_SUFFIXES:
            return self._asr_blocks(filename, content)
        return MediaExtractor.extract_blocks(self, filename, content)

    def _ocr_result(self, content: bytes, suffix: str):
        try:
            from io import BytesIO

            import numpy as np
            from paddleocr import PaddleOCR
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:
            raise RuntimeError(
                'OCR is unavailable. Install the "backend[multimodal]" dependencies.'
            ) from exc
        settings = get_settings()
        try:
            with Image.open(BytesIO(content)) as decoded:
                if decoded.format != _IMAGE_FORMATS[suffix]:
                    raise ValueError("Image format does not match the supported file type")
                if decoded.width * decoded.height > 16_000_000 or decoded.n_frames > 1:
                    raise ValueError("Image exceeds the supported pixel or frame budget")
                image = np.asarray(decoded.convert("RGB"))
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
            raise ValueError("The image could not be decoded within supported limits") from exc
        result = PaddleOCR(lang=settings.ocr_language).predict(image)
        return result

    @staticmethod
    def _ocr_lines(result) -> list[dict[str, Any]]:
        """Flatten a PaddleOCR result into line records with optional boxes."""
        lines: list[dict[str, Any]] = []
        for page in result:
            data = getattr(page, "json", page)
            if callable(data):
                data = data()
            if not isinstance(data, dict):
                continue
            data = data.get("res", data)
            texts = data.get("rec_texts")
            boxes = data.get("rec_boxes", data.get("rec_polys"))
            texts = [] if texts is None else texts
            boxes = [] if boxes is None else boxes
            for index, value in enumerate(texts):
                if not value:
                    continue
                record: dict[str, Any] = {"text": str(value), "line_index": index}
                if index < len(boxes):
                    box = boxes[index]
                    try:
                        record["bbox"] = [float(v) for v in box.flatten().tolist()]
                    except AttributeError:
                        record["bbox"] = [float(v) for v in box]
                lines.append(record)
        return lines

    def _ocr_blocks(self, content: bytes, suffix: str) -> list[dict[str, Any]]:
        lines = self._ocr_lines(self._ocr_result(content, suffix))
        blocks = [
            {
                "content": line["text"],
                "block_type": "ocr",
                "source_type": "image_ocr",
                "bbox": line.get("bbox"),
                "source_metadata": {"line_index": line["line_index"], "extractor": "paddleocr"},
            }
            for line in lines
        ]
        if not blocks:
            raise ValueError("OCR did not find readable text in the image")
        return blocks

    def _asr_blocks(self, filename: str, content: bytes) -> list[dict[str, Any]]:
        try:
            import av
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                'ASR is unavailable. Install the "backend[multimodal]" dependencies.'
            ) from exc
        settings = get_settings()
        with TemporaryDirectory(prefix="careerlens-media-") as directory:
            path = Path(directory) / Path(filename).name
            path.write_bytes(content)
            try:
                with av.open(path.as_posix()) as container:
                    formats = set(container.format.name.split(","))
                    if _CONTAINER_FORMATS[path.suffix.lower()] not in formats:
                        raise ValueError("Media format does not match the selected file type")
                    if not 1 <= len(container.streams.audio) <= 4:
                        raise ValueError("Media must have between one and four audio streams")
                    if container.duration is None or not (
                        0 < container.duration / av.time_base <= 1800
                    ):
                        raise ValueError("Media duration is unavailable or exceeds 30 minutes")
            except av.error.FFmpegError as exc:
                raise ValueError("The media container could not be decoded") from exc
            model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
            segments, info = model.transcribe(str(path), vad_filter=True)
            blocks: list[dict[str, Any]] = []
            for segment in segments:
                text = segment.text.strip()
                if not text:
                    continue
                blocks.append(
                    {
                        "content": text,
                        "block_type": "asr_segment",
                        "source_type": "asr",
                        "time_start": round(float(segment.start), 3),
                        "time_end": round(float(segment.end), 3),
                        "source_metadata": {
                            "extractor": "faster-whisper",
                            "model": settings.whisper_model,
                            "language": info.language,
                            "language_probability": round(info.language_probability, 4),
                        },
                    }
                )
        if not blocks:
            raise ValueError("ASR did not find readable speech in the media")
        return blocks

    def _ocr_image(self, content: bytes, suffix: str) -> tuple[str, dict[str, Any]]:
        blocks = self._ocr_blocks(content, suffix)
        text = "\n".join(block["content"] for block in blocks).strip()
        return text, {"extractor": "paddleocr", "line_count": len(blocks)}

    def _transcribe(self, filename: str, content: bytes) -> tuple[str, dict[str, Any]]:
        blocks = self._asr_blocks(filename, content)
        text = "\n".join(block["content"] for block in blocks).strip()
        first_meta = blocks[0]["source_metadata"]
        return text, {
            "extractor": "faster-whisper",
            "model": first_meta["model"],
            "language": first_meta["language"],
            "language_probability": first_meta.get("language_probability", 0.0),
            "segment_count": len(blocks),
        }


def parse_media(extractor: MediaExtractor, filename: str, content: bytes) -> ParsedDocument:
    structured = getattr(extractor, "extract_blocks", None)
    raw_blocks = (
        structured(filename, content)
        if structured is not None
        else MediaExtractor.extract_blocks(extractor, filename, content)
    )
    blocks = [ParsedBlock(block_index=index, **block) for index, block in enumerate(raw_blocks)]
    metadata = dict(blocks[0].source_metadata) if blocks else {}
    if blocks and blocks[0].block_type == "ocr":
        metadata["line_count"] = len(blocks)
    elif blocks and blocks[0].block_type == "asr_segment":
        metadata["segment_count"] = len(blocks)
    return ParsedDocument(doc_id="", blocks=blocks, source_type="media", metadata=metadata)


@lru_cache
def get_media_extractor() -> MediaExtractor:
    return OptionalMultimodalExtractor()
