from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.config import Settings


class VectorStore:
    def __init__(self, client: QdrantClient, settings: Settings):
        self.client = client
        self.settings = settings
        self.collection = settings.collection_name

    def setup(self):
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(
                    size=self.settings.dimensions, distance=models.Distance.COSINE
                ),
            )
        info = self.client.get_collection(self.collection)
        vector = info.config.params.vectors
        if not isinstance(vector, models.VectorParams) or vector.size != self.settings.dimensions:
            raise RuntimeError("Embedding dimensions do not match the Qdrant collection")
        self.client.create_payload_index(
            self.collection, "tenant_id", models.PayloadSchemaType.KEYWORD
        )
        self.client.create_payload_index(
            self.collection, "document_id", models.PayloadSchemaType.KEYWORD
        )

    @staticmethod
    def scope(tenant: str, document_ids: list[str] | None = None) -> models.Filter:
        conditions = [models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant))]
        if document_ids is not None:
            conditions.append(
                models.FieldCondition(key="document_id", match=models.MatchAny(any=document_ids))
            )
        return models.Filter(must=conditions)

    def insert(self, tenant: str, document: dict, chunks: list, vectors: list[list[float]]):
        if len(chunks) != len(vectors):
            raise ValueError("Embedding count does not match chunk count")
        points = [
            models.PointStruct(
                id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"{tenant}:{self.collection}:{document['document_id']}:{c.index}",
                    )
                ),
                vector=vector,
                payload={
                    "tenant_id": tenant,
                    "document_id": document["document_id"],
                    "filename": document["filename"],
                    "page": c.page,
                    "chunk": c.index,
                    "text": c.text,
                },
            )
            for c, vector in zip(chunks, vectors, strict=True)
        ]
        for start in range(0, len(points), 64):
            self.client.upsert(self.collection, points[start : start + 64], wait=True)

    def search(self, tenant: str, query: list[float], ready_ids: list[str]) -> list[dict]:
        if not ready_ids:
            return []
        result = self.client.query_points(
            self.collection,
            query=query,
            query_filter=self.scope(tenant, ready_ids),
            limit=self.settings.top_k,
            score_threshold=min(self.settings.score_threshold, 0.10)
            if self.settings.ai_backend == "fake"
            else self.settings.score_threshold,
            with_payload=True,
        )
        return [
            {**point.payload, "score": point.score, "citation": i}
            for i, point in enumerate(result.points, 1)
        ]

    def delete(self, tenant: str, document_id: str):
        self.client.delete(
            self.collection,
            models.FilterSelector(filter=self.scope(tenant, [document_id])),
            wait=True,
        )

    def healthy(self):
        self.client.get_collection(self.collection)
