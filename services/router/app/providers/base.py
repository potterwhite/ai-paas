"""Abstract base class for backend service providers."""

from abc import ABC, abstractmethod
from typing import Any


class BackendProvider(ABC):
    """Each backend (vLLM, Whisper, ComfyUI) implements this interface."""

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Return backend health status."""

    @abstractmethod
    async def forward_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Forward a request to the backend and return the response."""
