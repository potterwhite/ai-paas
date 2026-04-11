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
"""Model management — Phase 4.6, extended for multi-model switching.

Endpoints:
- GET  /models           — List local models on disk
- GET  /models/available — List registered vLLM model configurations (switchable)
- POST /models/switch    — Switch active LLM model
- POST /models/download  — Download model from HuggingFace
"""

import os
import subprocess
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.core.router_engine import detect_active_llm_model, switch_to_llm_model

router = APIRouter()


@router.get("/models")
async def list_models():
    """List available models mounted in MODELS_ROOT."""
    root = settings.MODELS_ROOT
    if not os.path.isdir(root):
        return {"models": [], "root": root, "error": "Models root not found"}
    models = []
    for entry in os.listdir(root):
        full_path = os.path.join(root, entry)
        if os.path.isdir(full_path):
            size_gb = 0
            try:
                size_bytes = sum(
                    os.path.getsize(os.path.join(dp, f))
                    for dp, dn, fn in os.walk(full_path) for f in fn
                )
                size_gb = round(size_bytes / (1024 ** 3), 2)
            except Exception:
                pass
            models.append({"name": entry, "path": full_path, "size_gb": size_gb})

    active_model = detect_active_llm_model()
    return {"models": models, "root": root, "active_model": active_model}


@router.get("/models/available")
async def list_available_models():
    """List registered vLLM model configurations that can be switched to.

    Returns the VLLM_MODELS registry with current status.
    """
    active_model = detect_active_llm_model()
    result = []
    for model_id, cfg in settings.VLLM_MODELS.items():
        # Check if model weights exist on disk
        model_dir = cfg["model_path"]
        weights_exist = os.path.isdir(model_dir)

        result.append({
            "model_id": model_id,
            "display_name": cfg.get("display_name", model_id),
            "container": cfg["container"],
            "model_path": cfg["model_path"],
            "aliases": cfg.get("aliases", []),
            "is_active": model_id == active_model,
            "weights_exist": weights_exist,
        })

    return {
        "models": result,
        "active_model": active_model,
        "default_model": settings.DEFAULT_LLM_MODEL,
    }


class ModelSwitch(BaseModel):
    model_id: str  # e.g. "qwen-32b", "gemma-4-26b"


@router.post("/models/switch")
async def switch_model(payload: ModelSwitch):
    """Switch the active vLLM model. Stops current model, starts target."""
    if payload.model_id not in settings.VLLM_MODELS:
        available = list(settings.VLLM_MODELS.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model_id '{payload.model_id}'. Available: {available}",
        )

    # Check if already running
    active = detect_active_llm_model()
    if active == payload.model_id:
        return {
            "status": "already_active",
            "model": payload.model_id,
            "message": f"{payload.model_id} is already running.",
        }

    # Check if model weights exist on disk before attempting switch
    model_path = settings.VLLM_MODELS[payload.model_id]["model_path"]
    if not os.path.isdir(model_path):
        raise HTTPException(
            status_code=400,
            detail=f"Model weights not found at '{model_path}'. Download the model first.",
        )

    # Perform the switch
    result = switch_to_llm_model(payload.model_id)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {
        "status": "switched",
        "model": payload.model_id,
        "actions": result.get("actions", []),
        "message": f"Switched to {payload.model_id}. Container starting up (~30-120s).",
    }


class ModelDownload(BaseModel):
    repo_id: str
    local_name: str = ""
    save_path: str = "/models"


@router.post("/models/download")
async def download_model(payload: ModelDownload):
    """Trigger model download from HuggingFace via huggingface-cli in a vLLM container."""
    local_name = payload.local_name or payload.repo_id.split("/")[-1].lower()
    target_dir = os.path.join(payload.save_path, local_name)

    if os.path.isdir(target_dir) and os.listdir(target_dir):
        return {
            "status": "exists",
            "repo_id": payload.repo_id,
            "local_dir": target_dir,
        }

    # Find a running vLLM container to exec into (any will do for downloads)
    active = detect_active_llm_model()
    container_name = (
        settings.VLLM_MODELS[active]["container"]
        if active
        else settings.VLLM_CONTAINER  # fallback
    )

    try:
        cmd = [
            "docker", "exec", container_name,
            "huggingface-cli", "download", payload.repo_id,
            "--local-dir", target_dir,
        ]
        if os.environ.get("HF_TOKEN"):
            cmd.extend(["--token", os.environ["HF_TOKEN"]])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode == 0:
            return {
                "status": "completed",
                "repo_id": payload.repo_id,
                "local_dir": target_dir,
            }
        return {
            "status": "failed",
            "repo_id": payload.repo_id,
            "error": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "repo_id": payload.repo_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
