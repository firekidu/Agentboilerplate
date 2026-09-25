import hashlib
from dataclasses import dataclass
from pathlib import PurePath
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from langgraph.checkpoint.postgres import PostgresSaver
from qdrant_client import QdrantClient

from app.config import Settings
from app.graph import build_graph
from app.models import FakeAI, OpenAIAI
from app.parsing import parse_and_chunk
from app.store import PostgresStore
from app.vectors import VectorStore


@dataclass
class Runtime:
    settings: Settings
    store: object
    vectors: VectorStore
    ai: object
    checkpointer: object
    graph: object = None

    def setup(self):
        self.store.setup()
        self.vectors.setup()
        self.graph = build_graph(
            self.ai, self.vectors, self.store, self.settings, self.checkpointer
        )

    def ingest(self, tenant: str, filename: str, data: bytes) -> dict:
        name = PurePath(filename.replace("\\", "/")).name[:180] or "document.txt"
        digest = hashlib.sha256(data).hexdigest()
        doc_id = str(uuid5(NAMESPACE_URL, f"{tenant}:{self.vectors.collection}:{digest}"))
        with self.store.tenant_lock(tenant):
            rows = self.store.documents(tenant, self.vectors.collection)
            existing = next((d for d in rows if d["document_id"] == doc_id), None)
            if existing and existing["status"] == "ready":
                return {**existing, "duplicate": True}
            if existing and existing["status"] == "deleting":
                raise HTTPException(409, "Finish deleting this document before uploading it again")
            if not existing and len(rows) >= self.settings.max_documents:
                raise HTTPException(409, "Document limit reached; delete unused documents first")
            chunks = parse_and_chunk(data, name, self.settings)
            doc = {
                "document_id": doc_id,
                "filename": name,
                "status": "indexing",
                "chunks": len(chunks),
            }
            self.store.save_document(tenant, self.vectors.collection, doc)
            # A retry replaces any incomplete points using the same deterministic IDs.
            self.vectors.delete(tenant, doc_id)
            embeddings = self.ai.embed([c.text for c in chunks])
            self.vectors.insert(tenant, doc, chunks, embeddings)
            doc["status"] = "ready"
            self.store.save_document(tenant, self.vectors.collection, doc)
            return {**doc, "duplicate": False}

    def delete_document(self, tenant: str, document_id: str):
        with self.store.tenant_lock(tenant):
            doc = next(
                (
                    d
                    for d in self.store.documents(tenant, self.vectors.collection)
                    if d["document_id"] == document_id
                ),
                None,
            )
            if not doc:
                raise HTTPException(404, "Document not found")
            doc["status"] = "deleting"
            self.store.save_document(tenant, self.vectors.collection, doc)
            self.vectors.delete(tenant, document_id)
            # Checkpoints contain questions, answers and intermediate passages.
            # Purge tenant conversations so a deleted document cannot survive in chat memory.
            for thread in self.store.threads(tenant):
                self.checkpointer.delete_thread(thread)
                self.store.remove_thread(tenant, thread)
            self.store.remove_document(tenant, self.vectors.collection, document_id)

    def close(self):
        self.vectors.client.close()
        self.store.close()


def create_runtime(settings: Settings) -> Runtime:
    store = PostgresStore(settings.database_url.get_secret_value())
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
        timeout=15,
        check_compatibility=False,
    )
    checkpointer = PostgresSaver(store.pool)
    checkpointer.setup()
    runtime = Runtime(
        settings,
        store,
        VectorStore(client, settings),
        FakeAI() if settings.ai_backend == "fake" else OpenAIAI(settings),
        checkpointer,
    )
    runtime.setup()
    return runtime
