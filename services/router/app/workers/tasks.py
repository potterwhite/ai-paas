"""Celery task definitions."""

from app.core.celery_app import celery_app
from app.core.router_engine import switch_to_llm_mode, switch_to_comfyui_mode


@celery_app.task(name="tasks.switch_gpu_mode")
def switch_gpu_mode(target: str) -> dict:
    """Switch GPU mode between LLM and ComfyUI via container management."""
    if target == "llm":
        return switch_to_llm_mode()
    elif target == "comfyui":
        return switch_to_comfyui_mode()
    return {"error": f"Unknown target mode: {target}"}


@celery_app.task(name="tasks.ensure_llm_mode")
def ensure_llm_mode() -> dict:
    """Ensure vLLM is running (call before processing LLM requests)."""
    return switch_to_llm_mode()


@celery_app.task(name="tasks.ensure_comfyui_mode")
def ensure_comfyui_mode() -> dict:
    """Ensure ComfyUI is running (call before processing visual requests)."""
    return switch_to_comfyui_mode()
