import asyncio
import hashlib
import math
from collections import Counter
from collections.abc import Sequence

from qdrant_client import QdrantClient, models

from app.models.evidence import Evidence
from app.retrieval.hybrid import tokenize
from app.retrieval.providers import EmbeddingProvider, RerankerProvider, score_documents

MAX_CANDIDATES = 80
MANIFEST_ID = "00000000-0000-0000-0000-000000000000"


class IndexIncompatible(RuntimeError):
    """Expected generation is absent, unverified, or incompatible."""


def collection_phase(
    client: QdrantClient, collection: str, fingerprint: str, dimension: int,
) -> str | None:
    if not client.collection_exists(collection):
        return None
    params = client.get_collection(collection).config.params
    dense = params.vectors.get("dense") if isinstance(params.vectors, dict) else None
    sparse = (params.sparse_vectors or {}).get("sparse")
    if (
        dense is None or dense.size != dimension or dense.distance != models.Distance.COSINE
        or sparse is None or sparse.modifier != models.Modifier.IDF
    ):
        raise IndexIncompatible("Collection has incompatible vector settings")
    rows = client.retrieve(collection, [MANIFEST_ID], with_payload=True)
    payload = rows[0].payload if rows else None
    if not payload or payload.get("fingerprint") != fingerprint:
        raise IndexIncompatible("Collection must be rebuilt for this embedding generation")
    phase = payload.get("phase")
    if phase not in {"building", "ready"}:
        raise IndexIncompatible("Collection has an unknown generation state")
    return phase


def sparse_vector(text: str) -> models.SparseVector:
    counts = Counter(tokenize(text))
    entries: dict[int, float] = {}
    for token, count in counts.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        index = int.from_bytes(digest, "big")
        entries[index] = entries.get(index, 0.0) + float(count)
    ordered = sorted(entries.items())
    return models.SparseVector(
        indices=[index for index, _ in ordered],
        values=[value for _, value in ordered],
    )


class QdrantEvidenceStore:
    def __init__(
        self,
        *,
        client: QdrantClient,
        collection_name: str,
        embedder: EmbeddingProvider,
        reranker: RerankerProvider,
        prefetch_limit: int = 20,
        fingerprint: str | None = None,
    ):
        self.client = client
        self.collection_name = collection_name
        self.embedder = embedder
        self.reranker = reranker
        self.prefetch_limit = prefetch_limit
        self.fingerprint = fingerprint or f"{embedder.name}:{embedder.dimension}"

    def ensure_collection(self, *, building: bool = False) -> None:
        expected_phase = "building" if building else "ready"
        phase = collection_phase(
            self.client, self.collection_name, self.fingerprint, self.embedder.dimension,
        )
        if phase is not None:
            if phase != expected_phase:
                raise IndexIncompatible(f"Collection is {phase}; need {expected_phase}")
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=self.embedder.dimension,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
        self.write_manifest(expected_phase)

    def write_manifest(self, phase: str) -> None:
        # Older Qdrant servers do not need a collection-metadata API. This
        # reserved point has no tenant ID and cannot enter any tenant prefetch.
        result = self.client.upsert(self.collection_name, points=[models.PointStruct(
            id=MANIFEST_ID,
            vector={"dense": [1.0] + [0.0] * (self.embedder.dimension - 1)},
            payload={"fingerprint": self.fingerprint, "phase": phase},
        )], wait=True, ordering=models.WriteOrdering.STRONG)
        if result.status != models.UpdateStatus.COMPLETED:
            raise IndexIncompatible("Collection manifest write was not confirmed")

    def index(self, evidence: Sequence[Evidence], *, building: bool = False) -> int:
        if not evidence:
            return 0
        self.ensure_collection(building=building)
        dense_vectors = self.embedder.embed_documents([item.content for item in evidence])
        points = [
            models.PointStruct(
                id=item.id,
                vector={
                    "dense": dense_vector,
                    "sparse": sparse_vector(item.content),
                },
                payload={
                    "user_id": item.user_id,
                },
            )
            for item, dense_vector in zip(evidence, dense_vectors, strict=True)
        ]
        result = self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
            ordering=models.WriteOrdering.STRONG,
        )
        if result.status != models.UpdateStatus.COMPLETED:
            raise RuntimeError("Index write was not confirmed")
        return len(points)

    def candidates(self, *, user_id: str, query: str, limit: int) -> list[tuple[str, float]]:
        if collection_phase(
            self.client, self.collection_name, self.fingerprint, self.embedder.dimension,
        ) != "ready":
            raise IndexIncompatible("Collection is not ready for retrieval")
        candidate_limit = min(MAX_CANDIDATES, max(self.prefetch_limit, limit * 4))
        tenant_filter = models.Filter(
            must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
        )
        response = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=self.embedder.embed_query(query),
                    using="dense",
                    limit=candidate_limit,
                    filter=tenant_filter,
                ),
                models.Prefetch(
                    query=sparse_vector(query),
                    using="sparse",
                    limit=candidate_limit,
                    filter=tenant_filter,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=tenant_filter,
            limit=candidate_limit,
            with_payload=False,
        )
        return [(str(point.id), float(point.score)) for point in response.points]

    def rank(
        self, *, query: str, candidates: list[tuple[str, float]],
        evidence: dict[str, dict], limit: int,
    ) -> list[dict]:
        return self.rank_with_trace(
            query=query, candidates=candidates, evidence=evidence, limit=limit,
        )[0]

    def rank_with_trace(
        self, *, query: str, candidates: list[tuple[str, float]],
        evidence: dict[str, dict], limit: int, allow_fallback: bool = True,
    ) -> tuple[list[dict], dict]:
        candidates = [(point, score) for point, score in candidates if point in evidence]
        rerank_scores, trace = score_documents(
            self.reranker, query,
            [evidence[point]["content"] for point, _ in candidates],
            allow_fallback=allow_fallback,
        )
        if len(rerank_scores) != len(candidates) or not all(map(math.isfinite, rerank_scores)):
            raise ValueError("Reranker returned invalid scores")
        ranked = sorted(
            zip(candidates, rerank_scores, strict=True),
            key=lambda pair: (-pair[1], -pair[0][1], pair[0][0]),
        )
        return [
            {
                "evidence_id": point,
                "score": round(score, 4),
                "rerank_score": round(float(rerank_score), 4),
                "source_type": evidence[point]["source_type"],
                "source_name": evidence[point]["source_name"],
                "content": evidence[point]["content"],
                "retrieval_method": "qdrant_dense_sparse_rrf_rerank",
            }
            for (point, score), rerank_score in ranked[:limit]
        ], trace

    async def aindex(self, evidence: Sequence[Evidence]) -> int:
        return await asyncio.to_thread(self.index, evidence)

    def delete(self, evidence_id: str, *, collection: str | None = None) -> None:
        delete_points(self.client, collection or self.collection_name, evidence_id=evidence_id)

    async def adelete(self, evidence_id: str, *, collection: str | None = None) -> None:
        await asyncio.to_thread(self.delete, evidence_id, collection=collection)

    def delete_user(self, user_id: str, *, collection: str | None = None) -> None:
        delete_points(self.client, collection or self.collection_name, user_id=user_id)

    async def adelete_user(self, user_id: str, *, collection: str | None = None) -> None:
        await asyncio.to_thread(self.delete_user, user_id, collection=collection)


def delete_points(
    client: QdrantClient, collection: str, *, evidence_id: str | None = None,
    user_id: str | None = None,
) -> None:
    if not client.collection_exists(collection):
        return
    if evidence_id is not None:
        selector = models.PointIdsList(points=[evidence_id])
    elif user_id is not None:
        selector = models.FilterSelector(filter=models.Filter(must=[
            models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
        ]))
    else:
        raise ValueError("An evidence ID or tenant is required for vector deletion")
    result = client.delete(
        collection_name=collection, points_selector=selector, wait=True,
        ordering=models.WriteOrdering.STRONG,
    )
    if result.status != models.UpdateStatus.COMPLETED:
        raise RuntimeError("Vector deletion was not confirmed")
