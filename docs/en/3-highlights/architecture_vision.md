# ai-paas — Architecture Vision

> Last updated: 2026-03-29
> **Related:** [中文版 →](../../zh/3-highlights/architecture_vision.md)

---

## Project Goal

Build a **personal AI Platform-as-a-Service** on a single RTX 3090 (24 GB VRAM) that
supports multiple AI applications with dynamic resource scheduling — without cloud costs.

The platform must serve four distinct use cases from one GPU:
1. **OpenClaw Agent Matrix** — high-concurrency LLM calls for an AI agent framework
2. **Web Translator / Subtitle Generator** — audio/video → subtitle pipeline with dual-track strategy (YouTube CC → Whisper fallback → LLM translation)
3. **AI Short Film / Video Generation** — CogVideo / SVD workflows via ComfyUI
4. **Digital Human** — LivePortrait / SadTalker facial animation via ComfyUI

---

## Target Architecture: Time-Division VRAM Scheduling

The long-term vision is **not** static partitioning. The goal is a time-division model
where a central router/orchestrator dynamically assigns full GPU access to the workload
that is actually running at any given moment.

```
                    ┌─────────────────────────────────────────────────────┐
                    │              ai-paas Orchestrator                   │
                    │   (Phase 3 — auto VRAM switch logic)                │
                    │   Phase 2 delivers manual GPU panel (/gpu page)     │
                    └────────────────────┬────────────────────────────────┘
                                         │ monitors VRAM, queues tasks
                    ┌────────────────────▼────────────────────────────────┐
                    │                 GPU: RTX 3090 24 GB                 │
                    └──────────────┬──────────────────┬───────────────────┘
                                   │                  │
          ┌────────────────────────▼───┐    ┌─────────▼──────────────────┐
          │  TEXT / AUDIO TIER         │    │  VISUAL TIER               │
          │  (always-on by default)    │    │  (on-demand, exclusive GPU) │
          │                            │    │                            │
          │  ┌──────────────────────┐  │    │  ┌──────────────────────┐  │
          │  │ LiteLLM :4000        │  │    │  │ ComfyUI              │  │
          │  │ └─→ vLLM :8000       │  │    │  │  CogVideoX / SVD     │  │
          │  │     └─→ Qwen 14B AWQ │  │    │  │  LivePortrait        │  │
          │  │ └─→ Whisper :9998    │  │    │  │  SadTalker           │  │
          │  └──────────────────────┘  │    │  └──────────────────────┘  │
          │  VRAM: ~17 GB + ~4 GB      │    │  VRAM: up to 24 GB         │
          └────────────────────────────┘    └────────────────────────────┘
                         │                              │
                         └──────────────┬───────────────┘
                                        │
                              All apps call ONE endpoint:
                              POST http://host:4000/v1/...
                              Or visit http://host:8080 (Web UI)
```

**Scheduling logic (Orchestrator — Phase 3):**
- Text/audio requests → served immediately by always-on LiteLLM+vLLM+Whisper
- Visual requests → queued; Orchestrator waits for text tier to go idle, stops it,
  starts ComfyUI, runs job, restores text tier
- Web UI shows VRAM status, active tier, queued jobs; supports manual override

**Phase 2 manual GPU panel (precursor to Orchestrator):**
- `ai_webapp /gpu` page: shows active containers + VRAM usage
- Manual start/stop buttons per container (Docker SDK)
- No auto-switching; user decides when to switch tiers

---

## Why These Architecture Choices Were Made

### Why vLLM instead of Xinference

**Decision date:** 2026-03-22
**Decision:** Abandon Xinference; use vLLM official Docker image directly.

Xinference creates a virtualenv subprocess which spawns vLLM EngineCore as a grandchild
process. This 3-level process nesting breaks `torch._C._cuda_init()` inside Docker. After
4 rounds of debugging with no resolution, vLLM's official Docker image was adopted instead.
vLLM exposes a native OpenAI-compatible API, eliminating the middleware layer entirely.

→ Full debugging history: `3-highlights/archived/xinference-debug-full-log.md`

### Why LiteLLM as the API gateway

LiteLLM provides three critical functions:
1. **Model aliasing** — apps call `"qwen"` not `/models/qwen2.5-14b-instruct-awq`; changing
   the underlying model requires only a 1-line config change, zero app changes
2. **Virtual key isolation** — each app gets a scoped key; the master key stays admin-only
3. **Web UI** — operational visibility into usage, keys, and model routing

The alternative (apps call vLLM directly) would hard-code model paths into every client.

### Why PostgreSQL instead of SQLite for LiteLLM

LiteLLM uses Prisma ORM which requires PostgreSQL (URL must start with `postgresql://`).
SQLite is not supported. This was discovered in Phase 1 testing and resolved by adding a
`postgres:16-alpine` container to the stack.

### Why `gpu_memory_utilization=0.7` (not higher, not lower)

- 0.5 (original): insufficient for 16k context window — KV cache OOM during OpenClaw runs
- 0.7 (~17 GB): satisfies OpenClaw's 16 000-token minimum and leaves ~7 GB for Phase 2 Whisper
- 0.8+: leaves too little headroom for Whisper co-run; risks OOM under concurrent load

### Why `--enable-auto-tool-choice --tool-call-parser hermes`

Qwen 2.5 uses Hermes-format tool call encoding. Without these flags, vLLM returns tool calls
in an unrecognised format, causing OpenClaw agent to receive 400 errors on every tool invocation.
These flags are non-negotiable as long as OpenClaw is a client.

### Why time-division instead of static VRAM partitioning

Static partitioning (e.g. vLLM=60%, ComfyUI=40%) would degrade both workloads. A video
generation model running in 40% of VRAM (~10 GB) produces lower quality output and runs
significantly slower than when given the full 24 GB. Similarly, reducing vLLM below 0.7
(~17 GB) breaks the 16k context requirement for OpenClaw.

Time-division solves this at the scheduling layer: each workload gets 100% of what it needs,
just not at the same instant. For a personal platform where workloads rarely overlap in
practice, this is the right trade-off.

---

## Three-Layer Architecture

```
Layer 3: Applications
  ┌──────────────┐  ┌──────────────────────────────┐  ┌──────────────┐  ┌──────────────┐
  │ OpenClaw LXC │  │ ai_webapp :8080 (Web UI)      │  │  AI Video    │  │DigitalHuman  │
  │192.168.0.11  │  │  / subtitle / translate / gpu │  │  (Phase 3)   │  │ (Phase 3)    │
  └──────┬───────┘  └──────────────┬────────────────┘  └──────┬───────┘  └──────┬───────┘
         │                         │                           │                  │
Layer 2: AI Inference + GPU Control (ai_paas_network)
  ┌──────▼─────────────────────────▼──────┐   ┌──────▼──────────────────▼───────┐
  │  TEXT/AUDIO TIER                      │   │  VISUAL TIER (Phase 3)          │
  │  LiteLLM :4000                        │   │  Orchestrator auto-switches GPU │
  │  └─→ vLLM :8000                       │   │  ComfyUI gets full 24 GB        │
  │      └─→ Qwen 14B AWQ (17GB)          │   └─────────────────────────────────┘
  │  └─→ Whisper :9998 (4GB)              │
  │  Phase 2: /gpu manual control panel   │
  └───────────────────────────────────────┘
         │
Layer 1: Infrastructure
  Ubuntu 24.04 VM · NVIDIA driver 580.x · CUDA 13.0 · Docker + Container Toolkit
  RTX 3090 24 GB VRAM · Docker network: ai_paas_network
```

---

## Guiding Principles

1. **Docker-only**: No bare-metal services. Every component is a container.
2. **Single gateway**: Applications never talk to vLLM directly; always LiteLLM.
3. **Model aliasing**: Changing a model is a 1-line config change, never a client change.
4. **Time-division VRAM**: Text inference and visual generation are never concurrent;
   each gets 100% of what it needs, scheduled by the Orchestrator.
5. **VRAM budget discipline**: Text tier = 0.7× budget max + Whisper headroom; visual = exclusive.
6. **Preserve history**: Failed approaches are archived, never deleted. The cost of
   re-learning a dead end is higher than the cost of keeping the debug log.
7. **Plugin-like extensibility**: Adding a new service = 1 docker-compose block + 1 litellm_config entry + 1 webapp route. Zero coupling to other services.
8. **Dual-track subtitle**: Always try fastest path first (YouTube CC via yt-dlp), fall back to GPU-heavy Whisper only when needed.
9. **Manual before auto**: Phase 2 gives manual GPU control; Phase 3 automates it. Never skip the manual step — it validates assumptions before automation.
