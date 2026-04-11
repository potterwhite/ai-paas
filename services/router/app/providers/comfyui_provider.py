"""ComfyUI BackendProvider — forwards visual generation requests."""

import httpx
from app.config import settings
from app.providers.base import BackendProvider


class ComfyUIProvider(BackendProvider):
    def __init__(self):
        self.base_url = settings.COMFYUI_BASE_URL

    async def health_check(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/system_stats")
                return {"status": "healthy" if resp.status_code < 400 else "unhealthy"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def forward_request(self, payload: dict) -> dict:
        """Forward a prompt/workflow to ComfyUI.

        Expects payload with 'prompt' key (ComfyUI API workflow dict).
        Returns the prompt_id that can be used to track progress.
        """
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self.base_url}/prompt",
                json={"prompt": payload.get("prompt", {}), "client_id": payload.get("client_id", "router")},
            )
            return resp.json()

    async def get_progress(self, prompt_id: str) -> dict:
        """Query ComfyUI for workflow execution progress."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.base_url}/history/{prompt_id}",
            )
            return resp.json()
