# Phase 4 — GPU Router / Orchestrator

> **Status:** Design complete, implementation ready | **Created:** 2026-04-05
> **Chinese version:** [中文 →](../../../zh/2-progress/phases/phase4/plan.md)

---

## Goal

Build a standalone `ai_router` service (FastAPI + Celery + Redis) to replace LiteLLM + PostgreSQL, achieving:
1. **Unified API entry** — All clients only connect to `ai_router:4001` (eventually switch to 4000)
2. **GPU exclusive scheduling** — vLLM and ComfyUI auto-switch, queuing support
3. **Extensible Provider architecture** — Each new service just needs a `BackendProvider` file

---

## Architecture

```
Client ──▶ ai_router:4001 (FastAPI)
              │
              ├─ LLM request → vLLM:8000 (direct / queued then forwarded)
              ├─ Audio request → Whisper:9998 (TTL auto-unload)
              └─ Visual request → ComfyUI:8188 (GPU switch then execute)
              │
              ├─ GPU scheduling / container start-stop / queuing ◀── Celery Workers
              └─ Redis (message queue) + SQLite (task persistence)
```

**Why remove LiteLLM:** LiteLLM only does 3 things in ai-paas — model alias mapping, key management, protocol forwarding. vLLM and Whisper both have OpenAI-compatible APIs, so no protocol translation is needed. Router covers all 3 things + adds GPU scheduling capability.

**Why standalone project (not a SynapseERP module):** Django's synchronous model is not suitable as a heavy API gateway + GPU scheduler. The two domains have unrelated responsibilities.

**Why Celery instead of Ray/SkyPilot:** Ray adds 10x complexity for single-GPU scenarios; SkyPilot targets multi-cloud. Celery + Redis is the lightest and already has visualization tools (Flower).

---

## Directory Structure

```
services/router/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py               # FastAPI entry (≤50 lines)
│   ├── config.py             # Config management
│   ├── api/routes/           # HTTP endpoints (gateway / tasks / queue / gpu)
│   ├── api/deps.py           # Auth middleware
│   ├── core/                 # Core logic (gpu_monitor / container_mgr / health_checker / router_engine)
│   ├── workers/              # Celery async tasks (celery_app / tasks)
│   ├── models/               # SQLAlchemy data models (task / response)
│   └── providers/            # ★ Extension point: one Provider file per backend service
│       ├── base.py           #   BackendProvider abstract base class
│       ├── vllm_provider.py
│       ├── whisper_provider.py
│       └── comfyui_provider.py
```

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `POST /api/v1/chat/completions` | OpenAI compatible, OpenClaw needs no changes |
| `POST /api/v1/audio/transcriptions` | Whisper direct |
| `GET/POST /api/v1/tasks[/{id}]` | Query task status |
| `GET /api/v1/queue` | Current queued tasks |
| `GET /api/v1/gpu` | GPU status |
| `GET/POST /api/v1/models[/switch|/download]` | Model management |
| `GET/POST/DELETE /api/v1/keys` | API Key management |
| `GET /api/v1/health` | Router health check |

---

## Iteration Path

| Step | Description | Status |
|---|---|---|
| **4.1** | Skeleton: FastAPI + Celery + Redis | ✅ Done | `d0f8862` |
| **4.2** | GPU monitoring + container status (pynvml + Docker SDK) | ✅ Done | `98bbf70` |
| **4.3** | LLM proxy: /api/v1/chat/completions → vLLM | ✅ Done | `453b28d` |
| **4.4** | GPU scheduler: Celery container switch + queue logic | ✅ Done | `8265dd3` |
| **4.5** | Migration: port → 4000, stop LiteLLM + PostgreSQL | ✅ Done | |
| **4.6** | Whisper + ComfyUI Provider + model management | ✅ Done | |

---

## VRAM Budget

| Scenario | Active Containers | VRAM |
|---|---|---|
| Text inference (default) | vLLM 32B AWQ | ~22 GB |
| Text + Whisper (14B fallback) | vLLM 14B + Whisper | ~21 GB |
| Visual generation | ComfyUI exclusive | Up to 24 GB |
| ⚠️ vLLM and ComfyUI **never run simultaneously** | | |
