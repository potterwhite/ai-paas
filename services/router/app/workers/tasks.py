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
