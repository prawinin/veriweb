import pytest
from pydantic import ValidationError
from veriweb.config import Settings


def test_empty_optional_endpoints_disable_model_and_embeddings() -> None:
    settings = Settings(model_url="", embeddings_model="")
    assert settings.model_url is None
    assert settings.embeddings_model is None


def test_endpoint_configuration_rejects_embedded_credentials() -> None:
    with pytest.raises(ValidationError):
        Settings(model_url="https://token:secret@model.example/v1")
