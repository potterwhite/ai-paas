# Copyright (c) 2026 PotterWhite
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

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

    # Wiki engine
    WIKI_SCHEMA_PATH: str = Field(
        default="_schema",
        description="Path to schema files relative to vault root",
    )
    WIKI_OUTPUT_PATH: str = Field(
        default="_wiki",
        description="Path to wiki output relative to vault root",
    )
    WIKI_MAX_CHUNK_TOKENS: int = Field(
        default=3500,
        description="Max tokens per source document chunk for ingest",
    )
    WIKI_MAX_OUTPUT_TOKENS: int = Field(
        default=1600,
        description="Max output tokens for LLM calls (must fit within model context window)",
    )
    WIKI_BATCH_CONCURRENCY: int = Field(
        default=3,
        description="Max concurrent ingest operations for batch mode",
    )
    WIKI_READ_ONLY: bool = Field(
        default=False,
        description="When True, all wiki write endpoints (ingest) return 403",
    )
    WIKI_LLM_MODEL: str = Field(
        default="qwen",
        description="LLM model name for wiki query and ingest (must be registered in Router)",
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


def get_wiki_path() -> Path:
    """Get the wiki output path as a Path object."""
    return get_vault_path() / settings.WIKI_OUTPUT_PATH


def get_schema_path() -> Path:
    """Get the schema path as a Path object."""
    return get_vault_path() / settings.WIKI_SCHEMA_PATH