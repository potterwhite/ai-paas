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
"""Router configuration — loaded from environment variables.

GPU container topology is NOT defined here. It lives in config/gpu-registry.json
(mounted at GPU_REGISTRY_PATH) so that Router, webapp and scripts/service.sh all
read one file instead of keeping their own copies of the container names.
"""

import json
import os
from pathlib import Path

# Single source of truth for every GPU container — see config/gpu-registry.json
GPU_REGISTRY_PATH: str = os.getenv("GPU_REGISTRY_PATH", "/config/gpu-registry.json")


def _load_gpu_registry(path: str) -> dict:
    """Read the GPU registry, or fail loudly.

    Deliberately no built-in fallback: silently booting with a stale hardcoded
    copy of the container list is the exact failure this registry exists to
    prevent — a wrong container name here means the Router stops the wrong
    thing and two processes end up fighting over 24 GB of VRAM.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(
            f"GPU registry not found at '{path}'. Mount config/gpu-registry.json "
            "into this container (see docker-compose.yml) or set GPU_REGISTRY_PATH."
        ) from None
    except json.JSONDecodeError as e:
        raise RuntimeError(f"GPU registry at '{path}' is not valid JSON: {e}") from None
    return raw


_REGISTRY = _load_gpu_registry(GPU_REGISTRY_PATH)

# Keys starting with "_" are documentation blocks, not container entries.
_GPU_CONTAINERS: dict = {
    k: v for k, v in _REGISTRY["containers"].items() if not k.startswith("_")
}


class Settings:
    # FastAPI
    APP_NAME: str = "ai-paas-gpu-router"
    HOST: str = "0.0.0.0"
    PORT: int = int(os.getenv("ROUTER_PORT", "4001"))

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://ai_router_redis:6379/0")

    # Celery
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://ai_router_redis:6379/1")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://ai_router_redis:6379/2")

    # Database (SQLite for task persistence)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./router.db")

    # vLLM — legacy single-model defaults (used as fallback)
    VLLM_BASE_URL: str = os.getenv("VLLM_BASE_URL", "http://ai_vllm_qwen:8000")
    VLLM_CONTAINER: str = os.getenv("VLLM_CONTAINER", "ai_vllm_qwen")

    # ── GPU topology, all derived from config/gpu-registry.json ──────────────
    # Every container that reserves the GPU, keyed by registry id.
    GPU_CONTAINERS: dict = _GPU_CONTAINERS

    # vLLM instances. Only one runs at a time (VRAM exclusive on a single GPU).
    VLLM_MODELS: dict = {
        k: v for k, v in _GPU_CONTAINERS.items() if v["type"] == "vllm"
    }

    # Non-LLM services that need the whole card (ComfyUI, HivisionIDPhotos, ...).
    # Starting any of these stops every vLLM, and starting a vLLM stops these.
    GPU_SERVICES: dict = {
        k: v for k, v in _GPU_CONTAINERS.items()
        if v["type"] == "service" and v["exclusive"]
    }

    # Default model to start when switching to LLM mode without specifying model
    DEFAULT_LLM_MODEL: str = _REGISTRY["default_llm_model"]

    # Whisper — HTTP endpoint only; the container name comes from the registry
    WHISPER_BASE_URL: str = os.getenv("WHISPER_BASE_URL", "http://ai_whisper:8000")

    # ComfyUI — HTTP endpoint only; the container name comes from the registry
    COMFYUI_BASE_URL: str = os.getenv("COMFYUI_BASE_URL", "http://ai_comfyui:8188")

    # Auth
    API_KEY: str = os.getenv("ROUTER_API_KEY", os.getenv("LITELLM_MASTER_KEY", "sk-change-me"))

    # Models
    MODELS_ROOT: str = os.getenv("MODELS_ROOT", "/models")

    # vLLM Docker network
    DOCKER_NETWORK: str = os.getenv("DOCKER_NETWORK", "ai_paas_network")


settings = Settings()
