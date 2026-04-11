# Phase 1 — Compute Hub

> Status: ✅ Complete | Completed: 2026-03-22 (infra), 2026-03-29 (cleanup)
> **Index:** [← progress.md](../../progress.md) | [中文版 →](../../../../zh/2-progress/phases/phase1/plan.md)

---

## Goal

Build a stable, GPU-accelerated LLM inference stack capable of serving OpenClaw agent tool
calls with a 14B parameter model. This is the foundation all future phases depend on.

---

## Architecture Decisions Made in This Phase

| Decision | Choice | Reason |
|---|---|---|
| Inference engine | vLLM (official Docker) | Xinference had unfixable CUDA spawn bug at 3-level process nesting depth |
| API gateway | LiteLLM | Model aliasing + virtual key management + Web UI + single control point |
| Database for LiteLLM | PostgreSQL | Prisma ORM (used by LiteLLM) rejects SQLite — PostgreSQL is mandatory |
| VRAM allocation | `gpu_memory_utilization=0.7` | Starts at 0.5 → raised to 0.7 to meet 16k context; leaves ~7 GB for Phase 2 Whisper |
| Tool call parser | `--tool-call-parser hermes` | Qwen 2.5 uses Hermes tool call format; without this, OpenClaw agent loops forever |
| Model | Qwen 2.5 14B Instruct AWQ (Int4) | Fits in 24 GB, strong reasoning, supports tool calls, OpenClaw-compatible |

For deeper rationale, see [`3-highlights/architecture_vision.md`](../../../3-highlights/architecture_vision.md).

---

## Step Log

| Step | Description | Commit |
|---|---|---|
| **1.1** | Initial Docker stack: vLLM + LiteLLM, Qwen 1.5B AWQ test model | `2203b16` |
| **1.2** | Add handoff doc with full system state | `ef4935a` |
| **1.3** | Switch to 14B production model; add PostgreSQL for LiteLLM UI; raise VRAM to 0.7; issue OpenClaw virtual key | `3f39fbf` |
| **1.4** | Enable tool-call support (`--enable-auto-tool-choice --tool-call-parser hermes`) | `bb99ea5` |
| **1.5** | Docs rebuild: AI-first bilingual structure + CLAUDE.md + phase plan files | `b8be598` |
| **1.6** | Directory cleanup: delete stale files, consolidate data/, add .env, bilingual README | `89360cc` `523fda3` |

---

## Verified Working ✅

- vLLM v0.18.0 running Qwen 2.5 14B Instruct AWQ (Int4) — 9.4 GB weights
- VRAM locked at 70% (~17 GB) via `gpu_memory_utilization=0.7`
- 16 384-token context window (OpenClaw minimum satisfied)
- LiteLLM gateway routing alias `"qwen"` to vLLM at `http://ai_vllm:8000/v1`
- LiteLLM Web UI at `:4000/ui` with PostgreSQL persistence
- OpenClaw (192.168.0.11) connected, agent tool calls working
- Portainer at `:9000`, Harbor at `:8080`

---

## Key Config Values (Phase 1 output state)

**vLLM flags (in `docker-compose.yml`):**
```
--model /models/qwen2.5-14b-instruct-awq
--gpu-memory-utilization 0.7
--max-model-len 16384
--enable-auto-tool-choice
--tool-call-parser hermes
--trust-remote-code
```

**LiteLLM alias (in `litellm_config.yaml`):**
```yaml
model_name: qwen
litellm_params:
  model: openai//models/qwen2.5-14b-instruct-awq
  api_base: http://ai_vllm:8000/v1
```

**OpenClaw virtual key:**
- Key: `sk-CsNbakApBdKkWut0qf2jVA` (alias: `openclaw-agent`)
- Scoped models: `["qwen"]`
- Note: use model string `"qwen"` (not `"litellm/qwen"` — see NEED_TO_DO for context)

---

## Known Issues / Resolved Problems

| Issue | Resolution |
|---|---|
| LiteLLM SQLite not supported | Fixed in 1.3 — switched to PostgreSQL |
| 1.5B test model too small for production | Fixed in 1.3 — replaced with 14B AWQ |
| Tool calls broken without hermes parser | Fixed in 1.4 |
| Xinference CUDA spawn bug | Resolved by abandoning Xinference (see `archived/`) |
| `VLLM_USE_V1=0` env var does not exist | Removed; replaced with `VLLM_ENABLE_V1_MULTIPROCESSING=0` |
| `VLLM_ENABLE_V1_MULTIPROCESSING=false` wrong type | Fixed: must be integer `0`, not string `false` |
