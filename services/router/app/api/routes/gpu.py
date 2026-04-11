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
"""GPU status + mode switching + container control — Phase 4.2/4.4.

Extended for multi-model vLLM support (Phase 5).
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.core.gpu_monitor import get_gpu_info
from app.core.container_mgr import (
    get_container_status,
    start_container,
    stop_container,
    restart_container,
)
from app.core.router_engine import (
    detect_gpu_mode,
    detect_active_llm_model,
    switch_to_llm_mode,
    switch_to_llm_model,
    switch_to_comfyui_mode,
)

router = APIRouter()

# Whitelist for safety — includes all vLLM model containers + whisper + comfyui
MANAGED_CONTAINERS = (
    [cfg["container"] for cfg in settings.VLLM_MODELS.values()]
    + ["ai_whisper", "ai_comfyui"]
)


class ContainerAction(BaseModel):
    action: str  # "start" | "stop" | "restart"
    container: str


class GpuModeAction(BaseModel):
    mode: str  # "llm" | "comfyui"
    model: str = ""  # optional: specific model_id for llm mode (e.g. "qwen-32b", "gemma-4-26b")


@router.get("/gpu")
async def gpu_status():
    """Return GPU metrics + managed container statuses + active model."""
    return {
        "gpus": get_gpu_info(),
        "containers": get_container_status(MANAGED_CONTAINERS),
        "current_mode": detect_gpu_mode(),
        "active_model": detect_active_llm_model(),
    }


@router.post("/gpu/containers")
async def control_container(action: ContainerAction):
    """Start, stop, or restart a managed container."""
    if action.container not in MANAGED_CONTAINERS:
        return {"error": f"Container '{action.container}' is not in whitelist"}

    handlers = {
        "start": start_container,
        "stop": stop_container,
        "restart": restart_container,
    }
    handler = handlers.get(action.action)
    if not handler:
        return {"error": f"Unknown action '{action.action}'"}

    ok = handler(action.container)
    return {"success": ok, "action": action.action, "container": action.container}


@router.post("/gpu/mode")
async def switch_gpu_mode(action: GpuModeAction):
    """Switch GPU mode: 'llm' or 'comfyui'. Stops conflicting containers.

    For 'llm' mode, optionally specify 'model' to pick a specific LLM.
    If model is omitted, uses the default or keeps the currently running model.
    """
    if action.mode == "llm":
        if action.model:
            result = switch_to_llm_model(action.model)
        else:
            result = switch_to_llm_mode()
    elif action.mode == "comfyui":
        result = switch_to_comfyui_mode()
    else:
        return {"error": f"Unknown mode '{action.mode}'. Use 'llm' or 'comfyui'."}

    # Propagate engine-level errors (e.g. missing model weights) as HTTP 400
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
