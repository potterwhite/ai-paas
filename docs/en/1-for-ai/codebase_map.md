# ai-paas — Codebase Map (AI Agent Quick Reference)

> **⚠️ FOR AI AGENTS — READ THIS FIRST**
> This document is the single source of truth for infrastructure structure.
> **Do NOT do a full directory scan** — read this file instead.
>
> **Maintenance rule:** Any AI agent that modifies a file listed here MUST update
> the relevant section in this document in the same commit/session.
>
> Last updated: 2026-04-05 (Phase 4 GPU Router architecture design complete; LiteLLM to be replaced in Phase 4.5)
>
> **Related:** [中文版 →](../../zh/1-for-ai/codebase_map.md)

---

## Repository Root Layout

```
/home/james/ai-paas/
├── CLAUDE.md                           ← Session entry point (auto-injected by Claude Code)
├── README.md                           ← ⭐ Project README (English) — open-source facing
├── docker-compose.yml                  ← PRIMARY CONFIG — all containers defined here
├── .env                                ← [git-ignored] Local secrets (copy from .env.example)
├── .env.example                        ← Template for .env — commit this, not .env
├── .gitignore                          ← Excludes models/, data/, .env, .claude/, __pycache__/
├── models/                             ← [git-ignored] Active model weights
│   ├── qwen2.5-14b-instruct-awq/       ←   PRODUCTION model (currently loaded in vLLM)
│   └── comfyui/                        ←   ComfyUI video/image model storage (see models/comfyui/ below)
├── services/
│   ├── webapp/                         ←   ai_webapp source (FastAPI + HTML/CSS)
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── static/style.css
│   └── comfyui/                        ←   ComfyUI setup scripts and workflows (Phase 3)
│       ├── install-nodes.sh            ←     Install custom nodes inside container
│       ├── download-models.sh          ←     Download CogVideoX-5B model weights
│       └── workflows/
│           ├── cogvideox5b_basic.json  ←     CogVideoX-5B text-to-video workflow
│           └── liveportrait_basic.json ←     LivePortrait digital human workflow
├── data/                               ← [git-ignored] Container runtime data
│   ├── router_redis/                   ←   Redis data (Phase 4 Celery)
│   ├── router_db/                      ←   Router SQLite (Phase 4)
│   └── comfyui_workdir/                ←   ComfyUI state + installed custom nodes
├── models/comfyui/                     ← [git-ignored] ComfyUI model directory (Phase 3)
│   ├── checkpoints/                    ←   Image diffusion checkpoints
│   ├── vae/                            ←   VAE models (cogvideox5b_vae.safetensors — single file)
│   ├── text_encoders/                  ←   T5-XXL FP8 encoder (t5xxl_fp8_e4m3fn.safetensors — single file)
│   ├── diffusion_models/               ←   CogVideoX-5B BF16 (cogvideox5b_bf16.safetensors — single file)
│   └── unet/                           ←   (reserved)
└── docs/
    ├── en/                             ← English documentation (AI-authoritative)
    │   ├── 00_INDEX.md                 ←   Navigation hub for all docs
    │   ├── 1-for-ai/
    │   │   ├── guide.md                ←   ⭐ Working rules, commit format, pitfalls, architecture facts
    │   │   ├── codebase_map.md         ←   ⭐ This file — infrastructure reference
    │   │   └── ai_docs_system_template.md  ←   Reference: template used to build this docs system
    │   ├── 2-progress/
    │   │   ├── progress.md             ←   ⭐ Phase index — all phases + commit hashes (read this, not git log)
    │   │   └── phases/
    │   │       ├── phase1/plan.md      ←   Phase 1: full plan, step log, architecture decisions (✅ complete)
    │   │       ├── phase2/plan.md      ←   Phase 2: Whisper deployment plan (✅ complete)
    │   │       ├── phase3/plan.md      ←   Phase 3: ComfyUI, video gen, digital human (✅ complete)
    │   │       └── phase4/plan.md      ←   Phase 4: GPU Router / Orchestrator (✅ complete)
    │   ├── 3-highlights/
    │   │   ├── architecture_vision.md  ←   Strategic design decisions and rationale
    │   │   └── archived/               ←   Superseded docs kept for history (never deleted)
    │   └── 4-for-beginner/
    │       └── quick_start.md          ←   Environment setup, first run, common errors
    └── zh/                             ← Chinese documentation (translation + active backlog)
        ├── 00_INDEX.md
        ├── README.md                   ←   ⭐ Chinese README (mirrors root README.md)
        ├── 1-for-ai/
        │   └── guide.md               ←   Chinese translation of en/1-for-ai/guide.md
        ├── 2-progress/
        │   ├── progress.md            ←   ⭐ Chinese progress index (mirrors en/2-progress/progress.md)
        │   ├── NEED_TO_DO.md          ←   ⭐ Active task backlog (open items only)
        │   ├── task-logs/             ←   Archived NEED_TO_DO files (fully-checked sessions)
        │   └── phases/
        │       ├── phase1/plan.md     ←   Phase 1 中文计划（✅ 完成）
        │       ├── phase2/plan.md     ←   Phase 2 中文计划（✅ 完成）
        │       ├── phase3/plan.md     ←   Phase 3 中文计划（✅ 完成）
        │       └── phase4/plan.md     ←   Phase 4 中文计划（✅ 完成）
        └── 3-highlights/
```

---

## File-by-File Reference

### `docker-compose.yml`
Defines all three production containers on network `ai_paas_network`.

**Service: `vllm` (container: `ai_vllm`)**
- Image: `vllm/vllm-openai:latest` (pinned to v0.18.0 at last test)
- Port mapping: host `9997` → container `8000` (9997 kept for backward compat)
- Model mount: `~/ai-paas/models:/models` — loads `/models/qwen2.5-14b-instruct-awq`
- Key flags:
  - `--gpu-memory-utilization 0.7` — reserves 70% of 24 GB (~17 GB) for vLLM
  - `--max-model-len 16384` — OpenClaw minimum; do not reduce below 16000
  - `--enable-auto-tool-choice --tool-call-parser hermes` — required for agent tool calls
  - `--trust-remote-code` — needed for Qwen2.5 tokenizer
  - `VLLM_ENABLE_V1_MULTIPROCESSING=0` — disables V1 multiprocessing (CUDA compat fix)
- `shm_size: 8gb`, `ipc: host` — required for vLLM tensor-parallel shared memory

**Service: `litellm-db` (container: `ai_litellm_db`)**
- Image: `postgres:16-alpine`
- Internal only (no host port exposed)
- Database / User / Password: read from `.env` (defaults: `litellm` / `litellm` / see `.env.example`)
- Volume: `~/ai-paas/data/litellm_pgdata:/var/lib/postgresql/data`
- Has healthcheck; `ai_litellm` waits for it to be healthy before starting

**Service: `litellm` (container: `ai_litellm`)**
- Image: `ghcr.io/berriai/litellm:main-latest`
- Port: `4000:4000` — the ONE port all applications call
- Config file: `litellm_config.yaml` mounted at `/app/config.yaml`
- Master key: set via `.env` → `LITELLM_MASTER_KEY` (default: `sk-1234` in `.env.example`)
- Web UI: `http://192.168.0.19:4000/ui` — credentials from `.env` (`UI_USERNAME` / `UI_PASSWORD`)
- Database: `DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@ai_litellm_db:5432/${POSTGRES_DB}`
  - ⚠️ SQLite is NOT supported — Prisma ORM requires PostgreSQL

---

### `litellm_config.yaml`
Three-section file. Only the `model_list` is critical:

```yaml
model_list:
  - model_name: qwen          # ← apps use this alias
    litellm_params:
      model: openai//models/qwen2.5-14b-instruct-awq   # openai/ prefix = OpenAI-compat route
      api_base: http://ai_vllm:8000/v1                  # inter-container hostname
      api_key: sk-none                                   # vLLM ignores auth; any value works

general_settings:
  master_key: sk-1234
```

- To add a new model (e.g. Whisper): add a new entry under `model_list`
- After editing: `docker compose restart ai_litellm` to reload config

---

## Active Containers (as of 2026-03-31)

| Container | Image | Host Port | Status | Purpose |
|---|---|---|---|---|
| `ai_vllm` | `vllm/vllm-openai:latest` | 9997→8000 | ✅ Running | LLM inference |
| `ai_litellm` | `ghcr.io/berriai/litellm:main-latest` | 4000→4000 | ✅ Running | API gateway |
| `ai_litellm_db` | `postgres:16-alpine` | internal | ✅ Running | LiteLLM persistence |
| `ai_whisper` | `ghcr.io/speaches-ai/speaches:latest-cuda` | 9998→8000 | ✅ Running | STT (faster-whisper) |
| `ai_webapp` | `ai-paas-webapp:latest` (built locally) | 8888→8080 | ✅ Running | Web UI (subtitle/translate/GPU panel) |
| `ai_comfyui` | `yanwk/comfyui-boot:cu130-slim-v2` | 8188→8188 | ⏸ Stopped (manual start only) | Visual generation (video/digital human) |
| `harbor-*` | harbor | 8080 | ✅ Running | Docker registry |

> **Note:** Portainer and Harbor are system-level containers not managed by `docker-compose.yml`.
> **Note:** `ai_whisper` image was `fedirz/faster-whisper-server` in original plan — repo renamed to `speaches-ai/speaches` in 2025.

---

## API Endpoints

### Production (apps always use this)
```
POST http://192.168.0.19:4000/v1/chat/completions
Authorization: Bearer <virtual-key>
Body: {"model": "qwen", "messages": [...]}
```

### Web UI Endpoints (ai_webapp :8888)
```
http://192.168.0.19:8888/           → Home: service cards + live VRAM widget
http://192.168.0.19:8888/subtitle   → Subtitle: YouTube URL or file upload → transcript/translation
http://192.168.0.19:8888/translate  → Translate: text → target language
http://192.168.0.19:8888/gpu        → GPU panel: VRAM bar + start/stop ai_vllm / ai_whisper
http://192.168.0.19:8888/models     → Model manager: list/download HF models + switch active model
http://192.168.0.19:8888/status     → JSON API: {vram_used_mb, vram_free_mb, vram_total_mb, containers[]}

# Model manager API (low-coupling, reusable)
GET  /api/models/list                          → list models in MODELS_ROOT dir
POST /api/models/download  {repo_id, local_name?} → start background HF download → {task_id}
GET  /api/models/progress/{task_id}            → poll download log + status
POST /api/models/switch    {model_name}        → returns compose change instructions
```

> VRAM data: webapp reads via `docker exec ai_vllm nvidia-smi` (no GPU passthrough needed).
> Container control: read-only docker.sock mount; whitelist = [ai_vllm, ai_whisper].

### Whisper STT (Phase 2)
```
# List installed models
GET  http://192.168.0.19:9998/v1/models

# Download a model (one-time, persists in named volume)
POST http://192.168.0.19:9998/v1/models/Systran%2Ffaster-whisper-large-v3

# Transcribe audio
POST http://192.168.0.19:9998/v1/audio/transcriptions
  -F file=@audio.wav
  -F model=Systran/faster-whisper-large-v3

# Browse available models
GET  http://192.168.0.19:9998/v1/registry
```

> ⚠️ Whisper model lazy-loads into GPU on first request; evicted after 5 min idle (ttl=300).
> VRAM peak during inference: ~22 GB (vLLM 17960 + Whisper ~4000). Stays within 24 GB.

### ComfyUI API (ai_comfyui :8188 — when running)
```
POST http://192.168.0.19:8188/prompt        → Submit workflow (JSON)
GET  http://192.168.0.19:8188/queue         → View queue status
POST http://192.168.0.19:8188/queue         → Clear/delete queue tasks
GET  http://192.168.0.19:8188/history       → View execution history
GET  http://192.168.0.19:8188/object_info   → List all available nodes
POST http://192.168.0.19:8188/interrupt     → Interrupt current job
WS   ws://192.168.0.19:8188/ws              → Real-time status updates
http://192.168.0.19:8188/                   → ComfyUI Web UI
```
> ⚠️ ai_comfyui must be manually started. Never start while ai_vllm is running.
> VRAM switching procedure: stop ai_vllm + ai_whisper → start ai_comfyui → do work → stop ai_comfyui → restart ai_vllm + ai_whisper

### OpenClaw-specific
```
API Base URL:  http://192.168.0.19:4000/v1
API Key:       sk-CsNbakApBdKkWut0qf2jVA   (alias: openclaw-agent)
Model Name:    qwen
```
> ⚠️ `litellm/qwen` is NOT a valid model name in LiteLLM 1.82.1+. Use `"qwen"` only.
> Verified 2026-03-28: `litellm/qwen` returns 400 "Invalid model name". `qwen` works.

### Debug only (vLLM direct)
```
POST http://192.168.0.19:9997/v1/chat/completions
Body: {"model": "/models/qwen2.5-14b-instruct-awq", "messages": [...]}
```

---

## GPU / VRAM Map

| Scenario | Containers Active | VRAM Used |
|---|---|---|
| Agent work (current default) | vLLM (Qwen 14B) | ~17 GB (70%) |
| Agent + Whisper idle | vLLM + Whisper (model evicted) | ~18 GB |
| Agent + Whisper inference (peak) | vLLM + Whisper large-v3 loaded | ~22 GB |
| Video generation (Phase 3) | ComfyUI only | up to 24 GB |
| Digital human (Phase 3) | ComfyUI only | up to 24 GB |

**VRAM Switching Procedure (when using Phase 3 visual features):**
1. Portainer → Stop `ai_vllm`
2. Start ComfyUI container (gets exclusive 24 GB)
3. Reverse to restore text inference

---

## Models on Disk

| Model | Path | Size | Status |
|---|---|---|---|
| Qwen 2.5 14B Instruct AWQ | `models/qwen2.5-14b-instruct-awq/` | ~9.4 GB | ✅ PRODUCTION (loaded) |
| CogVideoX-5B BF16 (single file) | `models/comfyui/diffusion_models/cogvideox5b_bf16.safetensors` | ~11 GB | ⏸ ComfyUI (manual start only) |
| T5-XXL FP8 text encoder | `models/comfyui/text_encoders/t5xxl_fp8_e4m3fn.safetensors` | ~4.6 GB | ⏸ ComfyUI (manual start only) |
| CogVideoX-5B VAE | `models/comfyui/vae/cogvideox5b_vae.safetensors` | ~823 MB | ⏸ ComfyUI (manual start only) |
| Qwen 2.5 1.5B Instruct AWQ | ~~`models/qwen2.5-1.5b-instruct-awq/`~~ | — | 🗑 Deleted 2026-04-02 (early test; no compose reference) |
| cogvideox5b HF subdir (duplicate) | ~~`models/comfyui/diffusion_models/cogvideox5b/`~~ | — | 🗑 Deleted 2026-04-02 (redundant copy of single-file) |
| t5xxl HF subdir (duplicate) | ~~`models/comfyui/text_encoders/t5xxl/`~~ | — | 🗑 Deleted 2026-04-02 (redundant full-precision copy) |
| Xinference cache | ~~`xinference_models/`~~ | — | ❌ Deleted — Xinference permanently abandoned |

> **Disk status (2026-04-02):** models/ = 26 GB. Disk: 104 GB used / 196 GB total (56%).
> **Planned upgrade:** Qwen 2.5 32B Instruct AWQ (~19 GB) — researched 2026-04-02; decision pending UI selection.

---

## Host Network Details

| Service | IP / URL | Port |
|---|---|---|
| This host (ai-paas VM) | 192.168.0.19 | — |
| OpenClaw LXC | 192.168.0.11 | — |
| LiteLLM gateway | 192.168.0.19 | 4000 |
| vLLM (debug) | 192.168.0.19 | 9997 |
| Portainer UI | 192.168.0.19 | 9000 |
| Harbor registry | 192.168.0.19 | 8080 |

---

## Key Architectural Patterns

1. **Single-gateway rule:** All client apps → LiteLLM :4000. vLLM :9997 is for diagnostics only.
2. **Model-alias pattern:** Apps use the alias `"qwen"` (or `"litellm/qwen"` for OpenClaw). Aliases are defined in `litellm_config.yaml` and can be updated without touching client code.
3. **VRAM-exclusive switching:** vLLM and ComfyUI never run simultaneously. Switching is manual (Portainer UI) until a Phase 3 automation is built.
4. **Virtual key isolation:** Each application gets its own LiteLLM virtual key scoped to specific model aliases. Master key `sk-1234` is admin-only.
5. **Docker network isolation:** All containers communicate via `ai_paas_network`. Inter-container calls use container hostnames (e.g. `http://ai_vllm:8000`), never host IP.
6. **Xinference is permanently abandoned:** Three rounds of debugging confirmed an unfixable upstream CUDA spawn bug. See `3-highlights/archived/` for full history.
