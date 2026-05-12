"""Embedding model for RAG service."""

import torch
from sentence_transformers import SentenceTransformer

from app.config import settings


class EmbeddingModel:
    """BGE embedding model wrapper."""

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
    ):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.device = device or settings.EMBEDDING_DEVICE
        self._model = None

    def _load_model(self):
        """Lazy load the embedding model."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def encode(self, texts: str | list[str], **kwargs) -> list[list[float]]:
        """
        Encode texts into embeddings.

        Args:
            texts: Single text or list of texts
            **kwargs: Additional arguments for sentence_transformers

        Returns:
            List of embedding vectors
        """
        model = self._load_model()

        if isinstance(texts, str):
            texts = [texts]

        embeddings = model.encode(texts, normalize_embeddings=True, **kwargs)

        return embeddings.tolist()

    def get_embedding_dim(self) -> int:
        """Get the dimension of embeddings."""
        model = self._load_model()
        return model.get_sentence_embedding_dimension()


embedding_model = EmbeddingModel()


def get_embedding(text: str) -> list[float]:
    """Get embedding for a single text."""
    return embedding_model.encode(text)[0]


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embeddings for multiple texts."""
    return embedding_model.encode(texts)