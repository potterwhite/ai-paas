"""Whisper BackendProvider — forwards transcription to ai_whisper."""

import io
import httpx
from app.config import settings
from app.providers.base import BackendProvider


class WhisperProvider(BackendProvider):
    def __init__(self):
        self.base_url = settings.WHISPER_BASE_URL

    async def health_check(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/health")
                return {"status": "healthy" if resp.status_code < 400 else "unhealthy"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def forward_request(self, file_bytes: bytes, file_name: str, params: dict) -> dict:
        """Forward a multipart/form-data transcription request."""
        async with httpx.AsyncClient(timeout=300) as client:
            files = {"file": (file_name, file_bytes, "audio/mpeg")}
            data = {"model": params.get("model", "Systran/faster-whisper-large-v3"),
                    "response_format": params.get("response_format", "json")}
            if params.get("language"):
                data["language"] = params["language"]
            if params.get("temperature") is not None:
                data["temperature"] = str(params["temperature"])

            resp = await client.post(
                f"{self.base_url}/v1/audio/transcriptions",
                files=files,
                data=data,
            )
            return resp.json()
