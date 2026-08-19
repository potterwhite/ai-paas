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
- "llm": One vLLM model running, every exclusive GPU service stopped
- <service_id>: One exclusive GPU service running (e.g. "comfyui", "idphoto"),
  all vLLM stopped
- "idle": Nothing GPU-intensive running

The card is a single 24 GB RTX 3090 with no MIG, so "exclusive" is literal:
exactly one of {a vLLM instance, a GPU service} may hold it at a time.

Both groups come from config/gpu-registry.json via settings — adding a GPU
service is a registry edit, not a code edit.
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


def _all_gpu_service_containers() -> list[str]:
    """Return all registered exclusive non-LLM GPU service container names."""
    return [cfg["container"] for cfg in settings.GPU_SERVICES.values()]


def detect_gpu_mode() -> str:
    """Detect current GPU mode from container status.

    Returns "llm", a GPU_SERVICES key ("comfyui", "idphoto", ...), or "idle".
    """
    vllm_containers = _all_vllm_containers()
    statuses = get_container_status(vllm_containers + _all_gpu_service_containers())
    status_map = {s["name"]: s["status"] for s in statuses}

    # Check if any vLLM is running
    for name in vllm_containers:
        if status_map.get(name) == "running":
            return "llm"

    for service_id, cfg in settings.GPU_SERVICES.items():
        if status_map.get(cfg["container"]) == "running":
            return service_id

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


def _stop_all_gpu_services(skip: str | None = None) -> list[str]:
    """Stop every running exclusive GPU service. `skip` leaves one service alone."""
    actions = []
    targets = {
        sid: cfg["container"]
        for sid, cfg in settings.GPU_SERVICES.items()
        if sid != skip
    }
    statuses = get_container_status(list(targets.values()))
    running = {s["name"] for s in statuses if s["status"] == "running"}

    for service_id, container in targets.items():
        if container in running:
            ok = stop_container(container)
            actions.append(f"stop_{service_id}={'ok' if ok else 'failed'}")

    return actions


def _creation_error(cfg: dict) -> str | None:
    """Return an actionable error if cfg's container was never created, else None.

    Every exclusive GPU container is profile-gated: compose creates it, the Router
    only starts/stops it. Checking this BEFORE freeing the card matters — otherwise
    we stop the current holder for a target that cannot start, leaving the GPU idle
    and both services down.
    """
    container = cfg["container"]
    statuses = get_container_status([container])
    if (statuses[0]["status"] if statuses else "not_found") != "not_found":
        return None

    service = cfg["compose_service"]
    profile = cfg.get("profile")
    hint = (
        f"docker compose --profile {profile} up -d --no-start {service}"
        if profile else f"docker compose up -d {service}"
    )
    return f"Container '{container}' does not exist yet. Create it first: {hint}"


def switch_to_llm_model(model_id: str) -> dict:
    """Switch to a specific LLM model. Stops GPU services and any other vLLM first."""
    if model_id not in settings.VLLM_MODELS:
        return {"error": f"Unknown model: {model_id}. Available: {list(settings.VLLM_MODELS.keys())}"}

    target = settings.VLLM_MODELS[model_id]

    # Guard: refuse to switch if model weights do not exist on disk
    model_path = target["model_path"]
    if not os.path.isdir(model_path):
        return {"error": f"Model weights not found at '{model_path}'. Download the model first."}

    err = _creation_error(target)
    if err:
        return {"error": err}

    result = {"mode": "llm", "model": model_id, "actions": []}

    # Stop every exclusive GPU service (ComfyUI, idphoto, ...) to free VRAM
    result["actions"].extend(_stop_all_gpu_services())

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


def switch_to_gpu_service(service_id: str) -> dict:
    """Switch to an exclusive non-LLM GPU service (ComfyUI, idphoto, ...).

    Stops every vLLM instance and every other GPU service, then starts the target.
    """
    if service_id not in settings.GPU_SERVICES:
        return {
            "error": f"Unknown GPU service: {service_id}. "
                     f"Available: {list(settings.GPU_SERVICES.keys())}"
        }

    target = settings.GPU_SERVICES[service_id]
    container = target["container"]

    err = _creation_error(target)
    if err:
        return {"error": err}

    result = {"mode": service_id, "actions": []}

    # Free the card: stop all vLLM, then every other exclusive GPU service
    result["actions"].extend(_stop_all_vllm())
    result["actions"].extend(_stop_all_gpu_services(skip=service_id))

    statuses = get_container_status([container])
    current = statuses[0]["status"] if statuses else "not_found"
    if current == "running":
        result["actions"].append("already_running")
    else:
        ok = start_container(container)
        result["actions"].append(f"start_{service_id}={'ok' if ok else 'failed'}")

    result["gpus"] = get_gpu_info()
    return result


def switch_to_comfyui_mode() -> dict:
    """Ensure ComfyUI is running, all vLLM stopped.

    Kept as a named alias so existing callers (workers/tasks.py, the webapp's
    one-click ComfyUI button) do not need to know about the generic registry.
    """
    return switch_to_gpu_service("comfyui")
