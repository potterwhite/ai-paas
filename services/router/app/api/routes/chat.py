"""OpenAI-compatible chat completions — Phase 4.3 with streaming.

Extended for multi-model vLLM support: dynamically routes to whichever
vLLM container is currently running.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import verify_api_key
from app.config import settings
from app.core.router_engine import get_active_vllm_base_url

router = APIRouter()

# Build alias map dynamically from VLLM_MODELS config
# e.g. {"qwen": "/models/qwen2.5-32b-instruct-awq", "gemma": "/models/gemma-4-26B-A4B-awq"}
MODEL_ALIASES: dict[str, str] = {}
for _mid, _cfg in settings.VLLM_MODELS.items():
    for _alias in _cfg.get("aliases", []):
        MODEL_ALIASES[_alias] = _cfg["model_path"]

RESOLVE_MODEL = lambda m: MODEL_ALIASES.get(m, m)


def _get_vllm_url() -> str:
    """Get the base URL of the currently running vLLM instance.

    Raises 503 if no vLLM model is running.
    """
    url = get_active_vllm_base_url()
    if not url:
        raise HTTPException(
            status_code=503,
            detail="No LLM model is currently running. Switch to LLM mode first via POST /v1/gpu/mode.",
        )
    return url


@router.post("/chat/completions")
async def chat_completions(request: Request, _=Depends(verify_api_key)):
    """OpenAI-compatible /v1/chat/completions → forwards to active vLLM.

    Supports both streaming (SSE) and non-streaming requests.
    """
    body = await request.json()
    body["model"] = RESOLVE_MODEL(body.get("model", ""))
    is_stream = body.get("stream", False)

    if not is_stream:
        # Non-streaming: single JSON response
        return await _forward_json(body)

    # Streaming: pass-through SSE from vLLM
    return StreamingResponse(
        _stream_sse(body),
        media_type="text/event-stream",
    )


async def _forward_json(body: dict) -> dict:
    """Forward request to active vLLM and return JSON response."""
    vllm_url = _get_vllm_url()
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{vllm_url}/v1/chat/completions",
            json=body,
        )
        return resp.json()


async def _stream_sse(body: dict):
    """Stream SSE events from active vLLM response."""
    vllm_url = _get_vllm_url()
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST",
            f"{vllm_url}/v1/chat/completions",
            json=body,
        ) as resp:
            async for line in resp.aiter_lines():
                if line:
                    yield f"{line}\n"
