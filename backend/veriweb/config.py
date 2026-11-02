from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VERIWEB_", env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore"
    )
    api_host: str = Field(default="127.0.0.1", min_length=1, max_length=253)
    api_port: int = Field(default=8000, ge=0, le=65535)
    model_url: str | None = None
    model_name: str = "local-model"
    model_key: SecretStr = SecretStr("")
    model_backend: Literal["unverified", "cpu", "rocm", "vulkan", "remote-amd"] = "unverified"
    model_timeout: float = Field(default=120, ge=5, le=300)
    model_context: int = Field(default=8192, ge=4096, le=65536)
    tavily_key: SecretStr = SecretStr("")
    tavily_url: str = "https://api.tavily.com/search"
    search_timeout: float = Field(default=15, ge=2, le=30)
    fetch_timeout: float = Field(default=12, ge=2, le=30)
    max_sources: int = Field(default=8, ge=3, le=8)
    follow_links: int = Field(default=2, ge=0, le=3)
    embeddings_model: str | None = None
    embedding_candidates: int = Field(default=96, ge=20, le=400)
    embeddings_device: Literal["cpu", "cuda"] = "cpu"
    cors_origins: list[str] = []
    run_timeout: int = Field(default=360, ge=30, le=600)

    @field_validator("model_url", "embeddings_model", mode="before")
    @classmethod
    def empty_optional(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("model_url", "tavily_url")
    @classmethod
    def valid_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Endpoint must be an HTTP URL without embedded credentials")
        return value.rstrip("/")
