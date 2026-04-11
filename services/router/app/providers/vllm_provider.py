"""vLLM BackendProvider — forwards chat completions to active vLLM instance.

Extended for multi-model support: dynamically resolves base URL and model aliases
from the VLLM_MODELS registry in config.
"""

import httpx
from app.config import settings
from app.core.router_engine import get_active_vllm_base_url
from app.providers.base import BackendProvider


# Build alias map dynamically from VLLM_MODELS config
_MODEL_ALIASES: dict[str, str] = {}
for _mid, _cfg in settings.VLLM_MODELS.items():
    for _alias in _cfg.get("aliases", []):
        _MODEL_ALIASES[_alias] = _cfg["model_path"]


class VLLMProvider(BackendProvider):
    def __init__(self):
        # Fallback to static config if no active model detected
        self.fallback_url = settings.VLLM_BASE_URL

    def _get_base_url(self) -> str:
        """Get base URL of the currently running vLLM instance."""
        return get_active_vllm_base_url() or self.fallback_url

    async def health_check(self) -> dict:
        try:
            base_url = self._get_base_url()
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{base_url}/health")
                return {"status": "healthy" if resp.status_code < 400 else "unhealthy"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def forward_request(self, payload: dict) -> dict:
        """Forward a chat completion request to vLLM. Returns SSE stream or JSON."""
        # Resolve model aliases dynamically (e.g. "qwen" → "/models/qwen2.5-32b-instruct-awq")
        model = payload.get("model", "")
        if model in _MODEL_ALIASES:
            payload["model"] = _MODEL_ALIASES[model]

        base_url = self._get_base_url()
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{base_url}/v1/chat/completions",
                json=payload,
            )
            return resp.json()
