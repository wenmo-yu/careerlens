import hashlib
import json
import math
from collections.abc import Sequence
from functools import lru_cache
from time import perf_counter
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

    def __init__(self, model_name: str, dimension: int, instruction: str, revision: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                'Qwen retrieval requires: pip install -e ".\\backend[ml]"'
            ) from exc
        self.dimension = dimension
        self.instruction = instruction
        self.model = SentenceTransformer(model_name, revision=revision)

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


class CascadingReranker:
    """Two-stage rerank: a cheap coarse pass narrows candidates, a fine pass
    scores only the shortlist. This is CareerLens's own design (neither
    WorkBuddy nor WeKnora ships a literal double reranker). Any stage failure
    degrades to a single lexical pass so retrieval never breaks.
    """

    def __init__(
        self,
        coarse: RerankerProvider,
        fine: RerankerProvider,
        coarse_top_k: int = 15,
        fine_top_k: int = 5,
    ) -> None:
        self._coarse = coarse
        self._fine = fine
        self._coarse_top_k = coarse_top_k
        self._fine_top_k = fine_top_k
        self.name = f"cascade:{coarse.name}->{fine.name}({coarse_top_k}/{fine_top_k})"

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        return self.score_with_trace(query, documents, allow_fallback=True)[0]

    def score_with_trace(
        self, query: str, documents: Sequence[str], *, allow_fallback: bool,
    ) -> tuple[list[float], dict]:
        documents = list(documents)
        if not documents:
            return [], {"stage": "empty", "effective": "none", "fine_count": 0}
        started = perf_counter()
        stage = "coarse"
        shortlist = []
        try:
            coarse_scores = self._coarse.score(query, documents)
            if len(coarse_scores) != len(documents) or not all(map(math.isfinite, coarse_scores)):
                raise ValueError("Invalid coarse scores")
            # Rank document positions by coarse score, keep the top slice.
            ranked = sorted(
                range(len(documents)),
                key=lambda index: coarse_scores[index],
                reverse=True,
            )[: self._coarse_top_k]
            shortlist = [documents[index] for index in ranked]
            stage = "fine"
            fine_scores = self._fine.score(query, shortlist)
            if len(fine_scores) != len(shortlist) or not all(map(math.isfinite, fine_scores)):
                raise ValueError("Invalid fine scores")
            # Put the fine-ranked top-k strictly above everything else, and
            # preserve coarse ordering for the rest. Using a disjoint score band
            # avoids mixing fine (cross-encoder) and coarse scales.
            result = [0.0] * len(documents)
            # Non-fine docs: coarse scores mapped into [0, 1) in coarse order.
            max_coarse = max((abs(score) for score in coarse_scores), default=1.0) or 1.0
            for index in range(len(documents)):
                result[index] = (coarse_scores[index] / max_coarse) * 0.5
            # Fine docs: map into [1, 2] preserving fine score order.
            fine_pairs = sorted(
                zip(ranked, fine_scores, strict=True), key=lambda pair: pair[1], reverse=True
            )[: self._fine_top_k]
            if fine_pairs:
                values = [value for _, value in fine_pairs]
                low, high = min(values), max(values)
                span = high - low
                for index, value in fine_pairs:
                    result[index] = 1.0 + ((value - low) / span if span else 0.5)
            return result, {
                "requested": self.name, "effective": self.name,
                "coarse_model": self._coarse.name, "fine_model": self._fine.name,
                "coarse_count": len(documents), "fine_count": len(shortlist),
                "fine_promoted_count": len(fine_pairs),
                "latency_ms": round((perf_counter() - started) * 1000, 2),
            }
        except (RuntimeError, ValueError, OSError) as exc:
            if not allow_fallback:
                raise
            lexical = LexicalReranker()
            scores = lexical.score(query, documents)
            return scores, {
                "requested": self.name, "effective": lexical.name,
                "fallback_stage": stage, "fallback_reason": type(exc).__name__,
                "coarse_count": len(documents), "fine_count": len(shortlist),
                "fine_promoted_count": 0,
                "latency_ms": round((perf_counter() - started) * 1000, 2),
            }


def score_documents(
    reranker: RerankerProvider, query: str, documents: Sequence[str], *, allow_fallback: bool,
) -> tuple[list[float], dict]:
    if isinstance(reranker, CascadingReranker):
        return reranker.score_with_trace(query, documents, allow_fallback=allow_fallback)
    if not documents:
        return [], {"requested": reranker.name, "effective": "none", "document_count": 0}
    started = perf_counter()
    trace = {"requested": reranker.name, "effective": reranker.name}
    try:
        scores = reranker.score(query, documents)
        if len(scores) != len(documents) or not all(map(math.isfinite, scores)):
            raise ValueError("Invalid reranker scores")
    except (RuntimeError, ValueError, OSError) as exc:
        if not allow_fallback or isinstance(reranker, LexicalReranker):
            raise
        lexical = LexicalReranker()
        scores = lexical.score(query, documents)
        trace.update(effective=lexical.name, fallback_reason=type(exc).__name__)
    return scores, {
        **trace, "document_count": len(documents),
        "latency_ms": round((perf_counter() - started) * 1000, 2),
    }


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.retrieval_provider == "qwen":
        return QwenEmbeddingProvider(
            settings.qwen_embedding_model,
            settings.embedding_dimension,
            settings.retrieval_query_instruction,
            settings.qwen_embedding_revision,
        )
    return HashEmbeddingProvider(settings.embedding_dimension)


@lru_cache
def get_reranker_provider() -> RerankerProvider:
    settings = get_settings()
    coarse: RerankerProvider
    fine: RerankerProvider
    if settings.rerank_stages_enabled:
        # Coarse is always the cheap lexical pass; fine uses the configured
        # model (Qwen when available, otherwise lexical).
        coarse = LexicalReranker()
        fine = (
            QwenReranker(settings.qwen_reranker_model, settings.retrieval_query_instruction)
            if settings.retrieval_provider == "qwen"
            else LexicalReranker()
        )
        return CascadingReranker(
            coarse,
            fine,
            settings.rerank_coarse_top_k,
            settings.rerank_fine_top_k,
        )
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


def embedding_fingerprint(settings: Settings) -> str:
    qwen = settings.retrieval_provider == "qwen"
    config = {
        "provider": settings.retrieval_provider,
        "model": settings.qwen_embedding_model if qwen else "hash-v1",
        "revision": settings.qwen_embedding_revision if qwen else "hash-v1",
        "dimension": settings.embedding_dimension,
        "distance": "Cosine",
        "normalize": True,
        "query_prefix": settings.retrieval_query_instruction if qwen else "",
        "document_preprocessing": "raw-v1" if qwen else "career-tokenize-v1",
        "sparse": "blake2b-32-terms-idf-v1",
    }
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
