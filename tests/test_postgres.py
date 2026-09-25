import os
from uuid import uuid4

import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from qdrant_client import QdrantClient

from app.models import FakeAI
from app.runtime import Runtime
from app.store import PostgresStore
from app.vectors import VectorStore


@pytest.mark.integration
def test_real_postgres_checkpoint_restart_and_quota(settings, tmp_path):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    tenant = "test-" + uuid4().hex
    thread = uuid4().hex
    vector_path = str(tmp_path / "qdrant")
    store = PostgresStore(url)
    saver = PostgresSaver(store.pool)
    saver.setup()
    rt = Runtime(
        settings, store, VectorStore(QdrantClient(path=vector_path), settings), FakeAI(), saver
    )
    rt.setup()
    doc = rt.ingest(tenant, "policy.txt", b"Refunds are available within 30 days of delivery.")
    store.register_thread(tenant, thread)
    result = rt.graph.invoke(
        {"question": "Refund period?", "tenant_id": tenant}, {"configurable": {"thread_id": thread}}
    )
    assert "30 days" in result["answer"]
    store.consume(tenant, "one", 1, 60)
    rt.close()
    # A fresh pool, graph and Qdrant client represent an application restart.
    store = PostgresStore(url)
    saver = PostgresSaver(store.pool)
    rt = Runtime(
        settings, store, VectorStore(QdrantClient(path=vector_path), settings), FakeAI(), saver
    )
    rt.setup()
    assert rt.graph.get_state({"configurable": {"thread_id": thread}}).values["history"]
    assert rt.store.documents(tenant, rt.vectors.collection)[0]["document_id"] == doc["document_id"]
    with pytest.raises(Exception) as error:
        store.consume(tenant, "one", 1, 60)
    assert error.value.status_code == 429
    rt.delete_document(tenant, doc["document_id"])
    assert saver.get_tuple({"configurable": {"thread_id": thread}}) is None
    rt.close()
