from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from app.core.config import get_settings

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
AUDIO_VIDEO_SUFFIXES = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".webm", ".mkv"}


class MediaExtractor(Protocol):
    def extract(self, filename: str, content: bytes) -> tuple[str, dict[str, Any]]: ...


class OptionalMultimodalExtractor:
    def extract(self, filename: str, content: bytes) -> tuple[str, dict[str, Any]]:
        suffix = Path(filename).suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            return self._ocr_image(content)
        if suffix in AUDIO_VIDEO_SUFFIXES:
            return self._transcribe(filename, content)
        raise ValueError(f"Unsupported media type: {suffix or 'unknown'}")

    def _ocr_image(self, content: bytes) -> tuple[str, dict[str, Any]]:
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
        lines: list[str] = []
        for page in result:
            data = getattr(page, "json", page)
            if callable(data):
                data = data()
            if isinstance(data, dict):
                data = data.get("res", data)
                lines.extend(str(value) for value in data.get("rec_texts", []) if value)
        text = "\n".join(lines).strip()
        if not text:
            raise ValueError("OCR did not find readable text in the image")
        return text, {"extractor": "paddleocr", "line_count": len(lines)}

    def _transcribe(self, filename: str, content: bytes) -> tuple[str, dict[str, Any]]:
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
            rows = [segment.text.strip() for segment in segments if segment.text.strip()]
        text = "\n".join(rows).strip()
        if not text:
            raise ValueError("ASR did not find readable speech in the media")
        return text, {
            "extractor": "faster-whisper",
            "model": settings.whisper_model,
            "language": info.language,
            "language_probability": round(info.language_probability, 4),
            "segment_count": len(rows),
        }


@lru_cache
def get_media_extractor() -> MediaExtractor:
    return OptionalMultimodalExtractor()
