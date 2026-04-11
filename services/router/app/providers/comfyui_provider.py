#
# Copyright (c) 2026 PotterWhite
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
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
