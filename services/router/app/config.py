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
"""Router configuration — loaded from environment variables."""

import os


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

    # Multi-model registry: model_id → container config
    # Each entry defines a vLLM instance with its own Docker container.
    # Only one runs at a time (VRAM exclusive on single GPU).
    VLLM_MODELS: dict = {
        "qwen-32b": {
            "container": "ai_vllm_qwen",
            "base_url": "http://ai_vllm_qwen:8000",
            "aliases": ["qwen"],
            "model_path": "/models/qwen2.5-32b-instruct-awq",
            "display_name": "Qwen 2.5 32B AWQ",
        },
        "gemma-4-26b": {
            "container": "ai_vllm_gemma",
            "base_url": "http://ai_vllm_gemma:8000",
            "aliases": ["gemma"],
            "model_path": "/models/gemma-4-26B-A4B-awq",
            "display_name": "Gemma 4 26B A4B (MoE)",
        },
    }

    # Default model to start when switching to LLM mode without specifying model
    DEFAULT_LLM_MODEL: str = "qwen-32b"

    # Whisper
    WHISPER_BASE_URL: str = os.getenv("WHISPER_BASE_URL", "http://ai_whisper:8000")
    WHISPER_CONTAINER: str = os.getenv("WHISPER_CONTAINER", "ai_whisper")

    # ComfyUI
    COMFYUI_BASE_URL: str = os.getenv("COMFYUI_BASE_URL", "http://ai_comfyui:8188")
    COMFYUI_CONTAINER: str = os.getenv("COMFYUI_CONTAINER", "ai_comfyui")

    # Auth
    API_KEY: str = os.getenv("ROUTER_API_KEY", os.getenv("LITELLM_MASTER_KEY", "sk-change-me"))

    # Models
    MODELS_ROOT: str = os.getenv("MODELS_ROOT", "/models")

    # vLLM Docker network
    DOCKER_NETWORK: str = os.getenv("DOCKER_NETWORK", "ai_paas_network")


settings = Settings()
