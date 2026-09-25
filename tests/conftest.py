import hashlib
import os
import warnings
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from qdrant_client import QdrantClient

from app.config import Settings
from app.main import create_app
from app.models import FakeAI
from app.runtime import Runtime
from app.store import MemoryStore
from app.vectors import VectorStore

KEY_A = "test-admin-a-" + "a" * 32
KEY_B = "test-admin-b-" + "b" * 32
KEY_READER = "test-reader-a-" + "r" * 32


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        database_url="postgresql://unused",
        qdrant_api_key="q" * 40,
        metrics_key="m" * 40,
        score_threshold=0.10,
        api_keys_json=[
            {"sha256": hashlib.sha256(key.encode()).hexdigest(), "tenant_id": tenant, "role": role}
            for key, tenant, role in [
                (KEY_A, "a", "admin"),
                (KEY_B, "b", "admin"),
                (KEY_READER, "a", "reader"),
            ]
        ],
    )


@pytest.fixture
def runtime(settings):
    remote = os.environ.get("TEST_QDRANT_URL")
    if remote:
        settings.qdrant_collection = "test_" + uuid4().hex[:10]
    qdrant = (
        QdrantClient(url=remote, api_key="q" * 40, check_compatibility=False)
        if remote
        else QdrantClient(":memory:")
    )
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Payload indexes.*")
        rt = Runtime(
            settings,
            MemoryStore(),
            VectorStore(qdrant, settings),
            FakeAI(),
            InMemorySaver(),
        )
        rt.setup()
    yield rt
    if remote:
        qdrant.delete_collection(rt.vectors.collection)
    rt.close()


@pytest.fixture
def client(runtime):
    with TestClient(create_app(runtime)) as test_client:
        yield test_client
