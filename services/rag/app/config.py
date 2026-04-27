"""RAG service configuration."""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class APIKeyInfo(BaseModel):
    """API key with LOA level."""
    key: str
    name: str
    loa_level: int = 1
    quota_daily: int = 100


class Settings(BaseSettings):
    """RAG service settings."""

    # Service
    RAG_PORT: int = Field(default=8081, description="RAG service port")
    RAG_HOST: str = Field(default="0.0.0.0", description="RAG service host")

    # Vault
    VAULT_PATH: str = Field(
        default="/vault",
        description="Path to Obsidian Vault (mounted volume)",
    )

    # ChromaDB
    CHROMA_DB_PATH: str = Field(
        default="/db/chroma",
        description="ChromaDB persistent storage path",
    )

    # Embedding
    EMBEDDING_MODEL: str = Field(
        default="BAAI/bge-small-zh-v1.5",
        description="HuggingFace embedding model name",
    )
    EMBEDDING_DEVICE: str = Field(
        default="cpu",
        description="Device for embedding model (cpu/cuda)",
    )

    # Router (LLM)
    ROUTER_BASE_URL: str = Field(
        default="http://ai_router:4000",
        description="Router API base URL",
    )
    ROUTER_API_KEY: str = Field(
        default="sk-change-me",
        description="Router API key for LLM calls",
    )

    # ChromaDB collection
    COLLECTION_NAME: str = Field(
        default="vault_notes",
        description="ChromaDB collection name",
    )

    # API keys (with LOA levels for RBAC)
    API_KEYS: list[APIKeyInfo] = Field(
        default_factory=lambda: [APIKeyInfo(key="sk-rag-default", name="default", loa_level=1)],
        description="Allowed API keys with LOA levels",
    )

    def get_api_key(self, token: str) -> Optional[APIKeyInfo]:
        """Get API key info by token."""
        for api_key in self.API_KEYS:
            if api_key.key == token:
                return api_key
        return None

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()


def get_vault_path() -> Path:
    """Get the Vault path as a Path object."""
    return Path(settings.VAULT_PATH)


def get_chroma_path() -> Path:
    """Get the ChromaDB path as a Path object."""
    return Path(settings.CHROMA_DB_PATH)