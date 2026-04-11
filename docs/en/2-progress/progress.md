# ai-paas — Progress Index

> Last updated: 2026-04-02
> **Related:** [中文版 →](../../zh/2-progress/progress.md)

This file is a navigation index only. Each phase has its own plan file with full
step logs, architecture decisions, config details, and open questions.

---

## Overall Status

| Phase | Description | Status | Plan |
|---|---|---|---|
| **Phase 1** | Compute Hub — vLLM + LiteLLM + base infrastructure | ✅ Complete | [phases/phase1/plan.md](phases/phase1/plan.md) · [中文](../../../zh/2-progress/phases/phase1/plan.md) |
| **Phase 2** | Audio/Video Translation — Whisper + Web UI (subtitle/translate/gpu pages) + manual GPU panel | ✅ Complete | [phases/phase2/plan.md](phases/phase2/plan.md) · [中文](../../../zh/2-progress/phases/phase2/plan.md) |
| **Phase 3** | Visual & Digital Human — ComfyUI + VRAM switching | ✅ Complete | [phases/phase3/plan.md](phases/phase3/plan.md) · [中文](../../../zh/2-progress/phases/phase3/plan.md) |
| **Phase 4** | GPU Router / Orchestrator — Unified API, exclusive GPU scheduling, replace LiteLLM | ✅ Complete | [phases/phase4/plan.md](phases/phase4/plan.md) · [中文](../../../zh/2-progress/phases/phase4/plan.md) |
| **Phase 5** | SynapseERP Integration — Agent-First ERP, ai-paas as infrastructure layer | ⏳ Planning | [phases/phase5/plan.md](phases/phase5/plan.md) · [中文](../../../zh/2-progress/phases/phase5/plan.md) |

**Currently active:** Phase 3 complete. Phase 4 implementation underway (4.1-4.4 done). Phase 5 vision documented.

---

## Phase 1 Commits (complete)

| Step | Description | Commit |
|---|---|---|
| 1.1 | Initial stack: vLLM + LiteLLM + 1.5B test model | `2203b16` |
| 1.2 | Handoff doc | `ef4935a` |
| 1.3 | 14B model + PostgreSQL + VRAM 0.7 + OpenClaw key | `3f39fbf` |
| 1.4 | Tool call support (`--enable-auto-tool-choice --tool-call-parser hermes`) | `bb99ea5` |
| 1.5 | Docs rebuild: AI-first bilingual structure + CLAUDE.md | `b8be598` |
| 1.6 | Directory cleanup: stale files deleted, data/ consolidated, .env, bilingual README | `89360cc` `523fda3` |

---

## Phase 2 Commits (in progress)

| Step | Description | Commit |
|---|---|---|
| 2.1 | Phase 2 plan written (`phases/phase2/plan.md`) | `b8be598` |
| 2.2 | Add `ai_whisper` (speaches:latest-cuda) to compose; CUDA test; VRAM co-existence verified (peak ~22GB, idle ~18GB, TTL eviction confirmed) | `ebc4daf` |
| 2.3–2.7 | Whisper LiteLLM route; webapp Dockerfile + FastAPI; subtitle/translate/gpu pages; responsive CSS | `ebc4daf` |
| 2.8 | End-to-end test + fix Whisper URL bug (was routing via LiteLLM instead of direct to ai_whisper) | `34155de` |
| 2.9 | Docs sync: codebase_map + progress.md mark Phase 2 ✅ Complete | this |

---

## Phase 3 Commits (complete)

| Step | Description | Commit |
|---|---|---|
| 3.2 | Add ai_comfyui to docker-compose; GPU passthrough verified | `b649156` |
| 3.3 | CogVideoX-5B workflow; model format fix | `fcd8039` |
| disk-cleanup | Deleted 3 redundant model dirs, freed 20 GB | `8b5cf46` |
| 32B upgrade | vLLM Qwen2.5-32B-AWQ; gpu_memory + max_model_len=10800 | `ab79c12`, `202e06f` |
| /models UI | WebUI model manager page | `122e2df` |

---

## Appendix — Failed Approaches

| Approach | Reason Failed | Reference |
|---|---|---|
| Xinference (xprobe/xinference:latest) | CUDA spawn bug: 3-level process nesting breaks `torch._C._cuda_init()` | [`archived/xinference-debug-full-log.md`](../3-highlights/archived/xinference-debug-full-log.md) |
| LiteLLM with SQLite | Prisma ORM rejects non-PostgreSQL URLs | Fixed in Phase 1.3 |
| `VLLM_USE_V1=0` env var | Does not exist in vLLM 0.13.0+ | [`archived/troubleshooting-log.md`](../3-highlights/archived/troubleshooting-log.md) |
| `VLLM_ENABLE_V1_MULTIPROCESSING=false` | Wrong type; must be `0` (integer) | Same as above |
