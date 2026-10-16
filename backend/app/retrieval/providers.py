import hashlib
import math
from collections.abc import Sequence
from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings
from app.retrieval.hybrid import tokenize


class EmbeddingProvider(Protocol):
    dimension: int
    name: str

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class RerankerProvider(Protocol):
    name: str

    def score(self, query: str, documents: Sequence[str]) -> list[float]: ...


class HashEmbeddingProvider:
    """Deterministic, dependency-free fallback for development and tests."""

    name = "hash-v1"

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def _encode(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimension
            sign = 1.0 if value & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._encode(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._encode(text)


class LexicalReranker:
    name = "lexical-v1"

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        query_tokens = set(tokenize(query))
        scores = []
        for document in documents:
            document_tokens = set(tokenize(document))
            overlap = len(query_tokens & document_tokens)
            denominator = max(len(query_tokens | document_tokens), 1)
            scores.append(overlap / denominator)
        return scores


class QwenEmbeddingProvider:
    name = "qwen3-embedding"

    def __init__(self, model_name: str, dimension: int, instruction: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                'Qwen retrieval requires: pip install -e ".\\backend[ml]"'
            ) from exc
        self.dimension = dimension
        self.instruction = instruction
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self.model.encode(
            list(texts),
            normalize_embeddings=True,
            truncate_dim=self.dimension,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vectors = self.model.encode(
            [text],
            prompt=self.instruction,
            normalize_embeddings=True,
            truncate_dim=self.dimension,
        )
        return vectors[0].tolist()


class QwenReranker:
    name = "qwen3-reranker"

    def __init__(self, model_name: str, instruction: str):
        try:
            import torch
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                'Qwen retrieval requires: pip install -e ".\\backend[ml]"'
            ) from exc
        self._torch = torch
        self.model = CrossEncoder(
            model_name,
            prompts={"career": instruction},
            default_prompt_name="career",
        )

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        scores = self.model.predict(
            [(query, document) for document in documents],
            activation_fn=self._torch.nn.Sigmoid(),
        )
        return [float(score) for score in scores]


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.retrieval_provider == "qwen":
        return QwenEmbeddingProvider(
            settings.qwen_embedding_model,
            settings.embedding_dimension,
            settings.retrieval_query_instruction,
        )
    return HashEmbeddingProvider(settings.embedding_dimension)


@lru_cache
def get_reranker_provider() -> RerankerProvider:
    settings = get_settings()
    if settings.retrieval_provider == "qwen":
        return QwenReranker(
            settings.qwen_reranker_model,
            settings.retrieval_query_instruction,
        )
    return LexicalReranker()


def provider_diagnostics(settings: Settings | None = None) -> dict[str, str | int]:
    selected = settings or get_settings()
    return {
        "provider": selected.retrieval_provider,
        "embedding_model": (
            selected.qwen_embedding_model if selected.retrieval_provider == "qwen" else "hash-v1"
        ),
        "reranker_model": (
            selected.qwen_reranker_model
            if selected.retrieval_provider == "qwen"
            else "lexical-v1"
        ),
        "dimension": selected.embedding_dimension,
    }
