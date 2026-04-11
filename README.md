# ai-paas

**Self-hosted AI platform on a single GPU — LLM inference, speech recognition, and video generation, all behind one OpenAI-compatible API endpoint.**

> No cloud. No per-token cost. Your data stays local.

[中文文档 →](docs/zh/README.md)

---

## What You Get

- **One API URL, one API key** — point any app or agent at `http://your-host:4000/v1` and it works
- **LLM inference** — Qwen 2.5 32B AWQ via vLLM, full tool-call support for agent loops
- **Speech-to-text** — Whisper (faster-whisper large-v3), lazy-load with TTL auto-eviction
- **Image & video generation** — ComfyUI with GPU exclusivity managed automatically
- **API key management** — scoped keys per app/agent; admin key for full access
- **Usage tracking** — per-key request logging in SQLite
- **Web UI** — subtitle extraction, translation, GPU control panel, model management

Everything runs as Docker containers. No bare-metal installs, no Python virtualenvs.

---

## Why Not Just Use Ollama?

| Feature | Ollama | ai-paas |
|---|:---:|:---:|
| OpenAI-compatible API | ✅ | ✅ |
| Virtual API keys (per-app isolation) | ❌ | ✅ |
| Usage tracking per key | ❌ | ✅ |
| Tool calls for agent loops (verified) | ⚠️ | ✅ |
| Whisper speech-to-text in same stack | ❌ | ✅ |
| Image / video generation (ComfyUI) | ❌ | ✅ |
| AWQ quantization (VRAM efficient) | ⚠️ | ✅ |
| GPU scheduling across workloads | ❌ | ✅ |

---

## Architecture

```
Your Apps / AI Agents
        │  POST /v1/chat/completions
        │  Authorization: Bearer <api-key>
        ▼
┌──────────────────────────────────────┐
│  Router  :4000                       │
│  ├─ API key auth + usage logging     │
│  ├─ GPU scheduling (Celery + Redis)  │
│  ├─→ vLLM :8000  (LLM inference)    │
│  └─→ Whisper :9998  (STT)           │
└──────────────────────────────────────┘

ComfyUI :8188  — exclusive GPU access, start/stop via WebUI
WebUI   :8888  — management dashboard
```

### GPU Budget (RTX 3090 · 24 GB)

| Mode | Active | VRAM |
|---|---|---|
| Text (default) | vLLM 32B AWQ | ~22 GB |
| Text + Speech | vLLM 14B + Whisper | ~17 + ~4 GB |
| Image / Video | ComfyUI (exclusive) | up to 24 GB |

vLLM and ComfyUI cannot run simultaneously — the GPU scheduler handles this automatically.

---

## Quick Start

**Requirements:** Docker + Docker Compose, NVIDIA GPU with container toolkit, model weights.

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/ai-paas.git
cd ai-paas

# 2. Configure secrets
cp .env.example .env
# Edit .env — set your own passwords and API keys

# 3. Place model weights
#    Download Qwen2.5-32B-Instruct-AWQ and place in:
#    models/qwen2.5-32b-instruct-awq/

# 4. Start the stack
docker compose up -d

# 5. Verify
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-1234" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"hello"}],"max_tokens":10}'
```

Web UI: `http://localhost:8888`

---

## Services & Ports

| Service | Port | Purpose |
|---|---|---|
| Router (API gateway) | 4000 | OpenAI-compatible endpoint, key auth, GPU scheduling |
| vLLM | 9997 (debug only) | LLM inference — use Router in production |
| Whisper | 9998 | Speech-to-text (transcription) |
| ComfyUI | 8188 | Image / video generation |
| Web UI | 8888 | Management dashboard |

---

## Tested On

| Component | Version |
|---|---|
| OS | Ubuntu 24.04 |
| GPU | NVIDIA RTX 3090 24 GB |
| NVIDIA Driver | 580.x |
| CUDA | 13.0 |
| Docker | 27.x + NVIDIA Container Toolkit |
| vLLM | 0.18.0 |

---

## Documentation

| Doc | Contents |
|---|---|
| [`docs/en/1-for-ai/codebase_map.md`](docs/en/1-for-ai/codebase_map.md) | Full infrastructure map — all containers, ports, config values |
| [`docs/en/4-for-beginner/quick_start.md`](docs/en/4-for-beginner/quick_start.md) | First-time setup walkthrough |
| [`docs/en/3-highlights/architecture_vision.md`](docs/en/3-highlights/architecture_vision.md) | Architecture decisions and rationale |

---

## License

MIT
