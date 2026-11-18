from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from app.core.config import get_settings

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
AUDIO_VIDEO_SUFFIXES = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".webm", ".mkv"}


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
            return self._ocr_image(content)
        if suffix in AUDIO_VIDEO_SUFFIXES:
            return self._transcribe(filename, content)
        raise ValueError(f"Unsupported media type: {suffix or 'unknown'}")

    def extract_blocks(self, filename: str, content: bytes) -> list[dict[str, Any]]:
        suffix = Path(filename).suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            return self._ocr_blocks(content)
        if suffix in AUDIO_VIDEO_SUFFIXES:
            return self._asr_blocks(filename, content)
        return MediaExtractor.extract_blocks(self, filename, content)

    def _ocr_result(self, content: bytes):
        try:
            from io import BytesIO

            import numpy as np
            from paddleocr import PaddleOCR
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError(
                'OCR is unavailable. Install the "backend[multimodal]" dependencies.'
            ) from exc
        settings = get_settings()
        image = np.asarray(Image.open(BytesIO(content)).convert("RGB"))
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
            texts = data.get("rec_texts", []) or []
            boxes = data.get("rec_boxes", data.get("rec_polys", [])) or []
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

    def _ocr_blocks(self, content: bytes) -> list[dict[str, Any]]:
        lines = self._ocr_lines(self._ocr_result(content))
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
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                'ASR is unavailable. Install the "backend[multimodal]" dependencies.'
            ) from exc
        settings = get_settings()
        with TemporaryDirectory(prefix="careerlens-media-") as directory:
            path = Path(directory) / Path(filename).name
            path.write_bytes(content)
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

    def _ocr_image(self, content: bytes) -> tuple[str, dict[str, Any]]:
        blocks = self._ocr_blocks(content)
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


@lru_cache
def get_media_extractor() -> MediaExtractor:
    return OptionalMultimodalExtractor()
