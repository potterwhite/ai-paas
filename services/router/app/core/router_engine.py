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
"""Router engine — GPU mode management and multi-model coordination.

GPU modes:
- "llm": One vLLM model running (qwen-32b, gemma-4-26b, etc.), ComfyUI stopped
- "comfyui": ComfyUI running, all vLLM stopped
- "idle": Nothing GPU-intensive running

Multi-model: Only one vLLM instance runs at a time (VRAM exclusive).
Router detects active model by checking which ai_vllm_* container is running.
"""

import os

from app.config import settings
from app.core.gpu_monitor import get_gpu_info
from app.core.container_mgr import (
    get_container_status,
    stop_container,
    start_container,
)


def _all_vllm_containers() -> list[str]:
    """Return all registered vLLM container names."""
    return [cfg["container"] for cfg in settings.VLLM_MODELS.values()]


def detect_gpu_mode() -> str:
    """Detect current GPU mode from container status."""
    vllm_containers = _all_vllm_containers()
    all_containers = vllm_containers + ["ai_comfyui"]
    statuses = get_container_status(all_containers)
    status_map = {s["name"]: s["status"] for s in statuses}

    # Check if any vLLM is running
    for name in vllm_containers:
        if status_map.get(name) == "running":
            return "llm"

    if status_map.get("ai_comfyui") == "running":
        return "comfyui"

    return "idle"


def detect_active_llm_model() -> str | None:
    """Return model_id of the currently running vLLM instance, or None."""
    vllm_containers = _all_vllm_containers()
    statuses = get_container_status(vllm_containers)

    for s in statuses:
        if s["status"] == "running":
            # Reverse lookup: container name → model_id
            for model_id, cfg in settings.VLLM_MODELS.items():
                if cfg["container"] == s["name"]:
                    return model_id
    return None


def get_active_vllm_base_url() -> str | None:
    """Return the base URL of the currently running vLLM, or None."""
    model_id = detect_active_llm_model()
    if model_id and model_id in settings.VLLM_MODELS:
        return settings.VLLM_MODELS[model_id]["base_url"]
    return None


def _stop_all_vllm() -> list[str]:
    """Stop all running vLLM containers. Returns list of action strings."""
    actions = []
    vllm_containers = _all_vllm_containers()
    statuses = get_container_status(vllm_containers)

    for s in statuses:
        if s["status"] == "running":
            # Find model_id for logging
            model_id = "unknown"
            for mid, cfg in settings.VLLM_MODELS.items():
                if cfg["container"] == s["name"]:
                    model_id = mid
                    break
            ok = stop_container(s["name"])
            actions.append(f"stop_{model_id}={'ok' if ok else 'failed'}")

    return actions


def switch_to_llm_model(model_id: str) -> dict:
    """Switch to a specific LLM model. Stops ComfyUI and any other vLLM first."""
    if model_id not in settings.VLLM_MODELS:
        return {"error": f"Unknown model: {model_id}. Available: {list(settings.VLLM_MODELS.keys())}"}

    target = settings.VLLM_MODELS[model_id]

    # Guard: refuse to switch if model weights do not exist on disk
    model_path = target["model_path"]
    if not os.path.isdir(model_path):
        return {"error": f"Model weights not found at '{model_path}'. Download the model first."}

    result = {"mode": "llm", "model": model_id, "actions": []}

    # Stop ComfyUI if running (free VRAM)
    comfyui_statuses = get_container_status(["ai_comfyui"])
    if comfyui_statuses and comfyui_statuses[0]["status"] == "running":
        ok = stop_container("ai_comfyui")
        result["actions"].append(f"stop_comfyui={'ok' if ok else 'failed'}")

    # Stop any running vLLM container (could be a different model)
    result["actions"].extend(_stop_all_vllm())

    # Start the target model's container
    ok = start_container(target["container"])
    result["actions"].append(f"start_{model_id}={'ok' if ok else 'failed'}")

    result["gpus"] = get_gpu_info()
    return result


def switch_to_llm_mode() -> dict:
    """Switch to LLM mode with the default or currently configured model."""
    # If a model is already running, keep it
    active = detect_active_llm_model()
    if active:
        return {"mode": "llm", "model": active, "actions": ["already_running"], "gpus": get_gpu_info()}

    # Otherwise start the default model
    return switch_to_llm_model(settings.DEFAULT_LLM_MODEL)


def switch_to_comfyui_mode() -> dict:
    """Ensure ComfyUI is running, all vLLM stopped."""
    result = {"mode": "comfyui", "actions": []}

    # Stop all vLLM containers first (frees VRAM)
    result["actions"].extend(_stop_all_vllm())

    # Start ComfyUI
    statuses = get_container_status(["ai_comfyui"])
    if statuses and statuses[0]["status"] != "running":
        ok = start_container("ai_comfyui")
        result["actions"].append(f"start_comfyui={'ok' if ok else 'failed'}")

    result["gpus"] = get_gpu_info()
    return result
