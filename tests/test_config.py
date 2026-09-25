import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_cannot_use_fake_ai(settings):
    values = settings.model_dump()
    values["environment"] = "production"
    with pytest.raises(ValidationError, match="Production requires"):
        Settings(_env_file=None, **values)


def test_embedding_model_changes_collection(settings):
    original = settings.collection_name
    settings.embedding_model = "another-model"
    assert settings.collection_name != original


def test_chunk_overlap_cannot_equal_chunk_size(settings):
    values = settings.model_dump()
    values["chunk_overlap"] = values["chunk_size"]
    with pytest.raises(ValidationError, match="smaller"):
        Settings(_env_file=None, **values)
