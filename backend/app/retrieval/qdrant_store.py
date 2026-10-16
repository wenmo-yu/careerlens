import asyncio
import hashlib
from collections import Counter
from collections.abc import Sequence

from qdrant_client import QdrantClient, models

from app.models.evidence import Evidence
from app.retrieval.hybrid import tokenize
from app.retrieval.providers import EmbeddingProvider, RerankerProvider


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
    ):
        self.client = client
        self.collection_name = collection_name
        self.embedder = embedder
        self.reranker = reranker
        self.prefetch_limit = prefetch_limit

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection_name):
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

    def index(self, evidence: Sequence[Evidence]) -> int:
        if not evidence:
            return 0
        self.ensure_collection()
        dense_vectors = self.embedder.embed_documents([item.content for item in evidence])
        points = [
            models.PointStruct(
                id=item.id,
                vector={
                    "dense": dense_vector,
                    "sparse": sparse_vector(item.content),
                },
                payload={
                    "evidence_id": item.id,
                    "user_id": item.user_id,
                    "source_type": item.source_type,
                    "source_name": item.source_name,
                    "content": item.content,
                    "chunk_index": item.chunk_index,
                    "metadata": item.source_metadata,
                },
            )
            for item, dense_vector in zip(evidence, dense_vectors, strict=True)
        ]
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )
        return len(points)

    def search(self, *, user_id: str, query: str, limit: int = 5) -> list[dict]:
        self.ensure_collection()
        candidate_limit = max(self.prefetch_limit, limit * 4)
        response = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=self.embedder.embed_query(query),
                    using="dense",
                    limit=candidate_limit,
                ),
                models.Prefetch(
                    query=sparse_vector(query),
                    using="sparse",
                    limit=candidate_limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id",
                        match=models.MatchValue(value=user_id),
                    )
                ]
            ),
            limit=candidate_limit,
            with_payload=True,
        )
        candidates = [point for point in response.points if point.payload]
        rerank_scores = self.reranker.score(
            query,
            [str(point.payload.get("content", "")) for point in candidates],
        )
        ranked = sorted(
            zip(candidates, rerank_scores, strict=True),
            key=lambda pair: (pair[1], pair[0].score),
            reverse=True,
        )
        return [
            {
                "evidence_id": str(point.payload["evidence_id"]),
                "score": round(float(point.score), 4),
                "rerank_score": round(float(rerank_score), 4),
                "source_type": str(point.payload["source_type"]),
                "source_name": str(point.payload["source_name"]),
                "content": str(point.payload["content"]),
                "retrieval_method": "qdrant_dense_sparse_rrf_rerank",
            }
            for point, rerank_score in ranked[:limit]
        ]

    async def aindex(self, evidence: Sequence[Evidence]) -> int:
        return await asyncio.to_thread(self.index, evidence)

    async def asearch(self, *, user_id: str, query: str, limit: int = 5) -> list[dict]:
        return await asyncio.to_thread(
            self.search,
            user_id=user_id,
            query=query,
            limit=limit,
        )

    def delete(self, evidence_id: str) -> None:
        if not self.client.collection_exists(self.collection_name):
            return
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=[evidence_id]),
            wait=True,
        )

    async def adelete(self, evidence_id: str) -> None:
        await asyncio.to_thread(self.delete, evidence_id)

    def delete_user(self, user_id: str) -> None:
        if not self.client.collection_exists(self.collection_name):
            return
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=user_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

    async def adelete_user(self, user_id: str) -> None:
        await asyncio.to_thread(self.delete_user, user_id)
