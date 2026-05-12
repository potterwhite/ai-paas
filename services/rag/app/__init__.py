"""Vault RAG app package."""

from app.config import settings
from app.rag_engine import search_vault, index_vault
from app.vault_writer import write_to_vault