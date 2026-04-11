# ai-paas — Quick Start Guide

> For new team members or anyone setting up a fresh session.
> **Related:** [中文版 →](../../zh/4-for-beginner/quick_start.md)

---

## Prerequisites

| Requirement | Value |
|---|---|
| Host OS | Ubuntu 24.04 |
| GPU | NVIDIA GeForce RTX 3090 (24 GB VRAM) |
| NVIDIA Driver | 580.126.09 (CUDA 13.0) |
| Docker | With NVIDIA Container Toolkit installed |
| Host IP | 192.168.0.19 (local network) |

---

## Check Current System State

Before doing anything, verify services are running:

```bash
# 1. Check all containers
docker ps

# Expected output includes: ai_vllm, ai_litellm, ai_litellm_db, portainer, harbor-*

# 2. Check GPU
nvidia-smi
# Expected: ~17,000 MiB used by VLLM::EngineCore process

# 3. Quick API smoke test
curl -s -X POST "http://192.168.0.19:4000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"hello"}],"max_tokens":10}' \
  | python3 -m json.tool
# Expected: JSON response with "qwen" choices
```

---

## Start the Stack (if containers are down)

```bash
cd /home/james/ai-paas
docker compose up -d

# Wait ~60 seconds for vLLM to load the 14B model
docker logs -f ai_vllm
# Ready when you see: "Application startup complete" or "Uvicorn running"
```

---

## Key URLs

| Service | URL | Credentials |
|---|---|---|
| LiteLLM API | http://192.168.0.19:4000/v1 | Bearer sk-1234 |
| LiteLLM Web UI | http://192.168.0.19:4000/ui | admin / sk-1234 |
| vLLM (debug) | http://192.168.0.19:9997/v1 | none |
| Portainer | http://192.168.0.19:9000 | (set on first login) |
| Harbor | http://192.168.0.19:8080 | (set on first login) |

---

## Issue a New API Key for an Application

```bash
curl -X POST "http://192.168.0.19:4000/key/generate" \
  -H "Authorization: Bearer sk-1234" \
  -H "Content-Type: application/json" \
  -d '{
    "key_alias": "my-app-name",
    "models": ["qwen"],
    "duration": null
  }'
# Returns: {"key": "sk-xxx...", ...}
```

---

## Connect an Application to the LLM

Use these values in your application config:

```
API Base URL:  http://192.168.0.19:4000/v1
API Key:       <your virtual key from above>
Model Name:    qwen
```

For OpenClaw specifically, use model name `litellm/qwen`.

---

## Add a New Model to the Stack

1. Download the model to `~/ai-paas/models/<model-dir>/`
2. Edit `docker-compose.yml` → change `--model` path in the `vllm` service command
3. Edit `litellm_config.yaml` → update `model` path under `model_list`
4. Restart: `docker compose restart ai_vllm ai_litellm`

---

## Common First-Time Errors

| Error | Cause | Fix |
|---|---|---|
| `curl` returns connection refused on :4000 | `ai_litellm` not started | `docker compose up -d` |
| `ai_vllm` loops on startup | Model path wrong or model not downloaded | Check `docker logs ai_vllm`; verify `models/` directory |
| `CUDA out of memory` | Another process using GPU | `nvidia-smi` to find PID, stop other containers |
| LiteLLM Web UI won't log in | PostgreSQL not healthy yet | `docker ps` — wait for `ai_litellm_db` to show `healthy` |
| vLLM returns 400 on tool calls | Tool call flags not set | Verify `--enable-auto-tool-choice --tool-call-parser hermes` in compose |
| `DATABASE_URL` error in LiteLLM | SQLite attempted | Use `postgresql://...` only; SQLite is not supported |

---

## Read Before Working

```
docs/en/1-for-ai/guide.md          — rules, commit format, pitfalls
docs/en/1-for-ai/codebase_map.md   — all files, containers, APIs
docs/en/2-progress/progress.md     — current phase status
docs/zh/2-progress/NEED_TO_DO.md   — active task backlog
```
