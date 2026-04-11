# Phase 3 — Visual Generation & Digital Human (Time-Division Scheduling)

> Status: ✅ Complete | Completed: 2026-04-02
> **Index:** [← progress.md](../../progress.md) | [中文版 →](../../../../zh/2-progress/phases/phase3/plan.md)

---

## Goal

Deploy visual AI services (video generation, digital human) AND build an Orchestrator that
enables **automatic time-division GPU scheduling** — routing workloads to the appropriate
tier without manual intervention.

**Two sub-goals:**
1. **Content goal** — Working ComfyUI pipelines for video generation and digital human
2. **Infrastructure goal** — Orchestrator with auto VRAM switching (builds on Phase 2 manual GPU panel)

> **Boundary with Phase 2:**
> Phase 2 delivers a **manual GPU control panel** (`/gpu` page in `ai_webapp`): the user can see
> VRAM usage and manually start/stop containers. Phase 3 automates that: the Orchestrator watches
> the queue, drains the active tier, switches containers, and restores without human intervention.

---

## Why Time-Division (not static partitioning)

Static VRAM partitioning (vLLM=60%, ComfyUI=40%) would degrade both workloads:
- ComfyUI in ~10 GB produces lower quality output and runs significantly slower
- vLLM below 0.7× (~17 GB) breaks the 16k context requirement for OpenClaw

**Time-division scheduling** gives each workload 100% of what it needs, at different times:
- **Text/Audio tier** (always-on by default): vLLM (~17 GB) + Whisper (~4 GB)
- **Visual tier** (on-demand, exclusive): ComfyUI gets full 24 GB; text tier is paused

For a personal platform where workloads rarely overlap in practice, this is the optimal approach.

---

## Architecture

```
                    ┌─────────────────────────────────────────────────────┐
                    │              ai-paas Orchestrator                   │
                    │   (new service: web UI + VRAM switch automation)    │
                    └──────────┬──────────────────────┬───────────────────┘
                               │ monitors              │ issues commands
              ┌────────────────▼───┐        ┌──────────▼─────────────────┐
              │  TEXT/AUDIO TIER   │        │  VISUAL TIER               │
              │  (default active)  │        │  (activated on demand)     │
              │                    │        │                            │
              │  LiteLLM :4000     │        │  ComfyUI                   │
              │  └─→ vLLM :8000    │        │  └─→ CogVideoX / SVD       │
              │  └─→ Whisper :9998 │        │  └─→ LivePortrait          │
              │                    │        │  └─→ SadTalker             │
              │  VRAM: ~21 GB      │        │  VRAM: up to 24 GB         │
              └────────────────────┘        └────────────────────────────┘
```

**Switching flow (Orchestrator-controlled):**
1. Visual task submitted to Orchestrator
2. Orchestrator waits for text tier to drain (no in-flight requests)
3. Stop `ai_vllm` + `ai_whisper`
4. Start `ai_comfyui`
5. Execute visual job
6. Stop `ai_comfyui`
7. Restart `ai_vllm` + `ai_whisper`
8. Orchestrator resumes routing text requests

---

## Step Plan

| Step | Description | Status | Commit |
|---|---|---|---|
| **3.1** | Write Phase 3 plan (this file); establish time-division architecture | ✅ Done | `b8be598`, `fa9e4e9` |
| **3.2** | Select ComfyUI Docker image; test GPU passthrough + VRAM read | ✅ Done | `b649156` |
| **3.3** | Build CogVideoX-5B workflow in ComfyUI; fix model format | ✅ Done | `fcd8039` |
| **disk-cleanup** | Delete 3 redundant model dirs, freed 20 GB | ✅ Done | `8b5cf46` |
| **32B upgrade** | Upgrade vLLM to Qwen2.5-32B-AWQ; gpu_memory 0.7→0.95 | ✅ Done | `ab79c12`, `202e06f` |
| **/models UI** | WebUI /models page — HuggingFace model manager | ✅ Done | `122e2df` |
| **3.4** | Build LivePortrait / SadTalker workflow (digital human) | ⬜ Pending | — |
| **3.5** | Build Orchestrator: auto-switching logic | ✅ Merged into Phase 4.4 `8265dd3` |
| **3.6** | Auto-switch Web UI in `/gpu` page | ✅ Phase 2 `/gpu` page already meets manual switch needs |
| **3.7** | Expose ComfyUI API via Orchestrator | ✅ Merged into Phase 4 `8265dd3` |
| **3.8** | Update `codebase_map.md` | ✅ Done | `cad9916` |

---

## Orchestrator Spec (Step 3.5–3.6)

**Relationship to Phase 2:**
Phase 2 builds a manual `/gpu` page in `ai_webapp`. Phase 3 adds automation on top of it —
the same Docker SDK integration, extended with a queue processor and drain logic.

**Minimum viable Orchestrator:**

| Feature | Description |
|---|---|
| Web UI | Shows: active tier (TEXT / VISUAL), current VRAM usage, queued jobs |
| Manual switch | Button to manually trigger tier switch (for immediate control) |
| Auto switch | Detects idle text tier, starts queued visual job automatically |
| Drain wait | Checks LiteLLM in-flight request count before switching |
| Restore | After visual job completes, automatically restores text tier |

**Implementation plan:**
- Small Python FastAPI service (`ai_orchestrator` container)
- Uses Docker SDK to stop/start containers (`docker.from_env()`)
- Polls `nvidia-smi` or Docker stats for VRAM usage
- Simple queue (in-memory or Redis) for visual job requests
- Web UI: lightweight HTML+JS (no heavy framework needed)

---

## VRAM Budget

| Scenario | Active Containers | VRAM |
|---|---|---|
| Text/Audio tier (default) | `ai_vllm` + `ai_whisper` | ~17 + ~4 = ~21 GB |
| Visual tier (on-demand) | `ai_comfyui` | up to 24 GB |
| Transition state | neither (draining) | minimal |

⚠️ **Never run vLLM and ComfyUI simultaneously.** Both claim large VRAM blocks; one will OOM.

---

## Candidate Models / Tools

| Use Case | Model | Notes |
|---|---|---|
| Video generation | CogVideoX | Open-source, ComfyUI plugin available |
| Video generation (alt) | Stable Video Diffusion (SVD) | Lower VRAM, shorter clips |
| Digital human | LivePortrait | Portrait + audio → talking video |
| Digital human (alt) | SadTalker | Alternative, also ComfyUI-compatible |

---

## Open Questions (resolve before Step 3.2)

- [x] Which ComfyUI Docker image to use → **`yanwk/comfyui-boot:cu130-slim-v2`** (CUDA 13.0 native, slim/no bundled models)
- [x] CUDA 13 compatibility for ComfyUI + CogVideoX → **Confirmed**: yanwk cu130 tag uses PyTorch 2.11 with CUDA 13.0 wheels; RTX 3090 + driver 580 fully compatible
- [ ] Orchestrator implementation: FastAPI vs Go vs minimal shell wrapper
- [ ] Drain detection: poll LiteLLM `/health/readiness` or DB SpendLogs?

## Image Selection Decision (2026-03-31)

- **Selected**: `yanwk/comfyui-boot:cu130-slim-v2`
  - Reason: CUDA 13.0 native (matches host driver 580); slim = no bundled models; we mount our own
  - Original plan `ai-dock/comfyui` was CUDA 12.x based — functional but less clean on driver 580
- **Primary video model**: CogVideoX-5B (~13-14 GB with cpu_offload + tiling; fits 24 GB)
- **Primary digital human**: LivePortrait (< 4 GB, GAN architecture, very fast)

---

## Risks

| Risk | Mitigation |
|---|---|
| ComfyUI CUDA 13 incompatibility | Test with minimal node graph before installing video models |
| CogVideoX VRAM requirement > 24 GB | Fall back to SVD or use fp8 quantization |
| Orchestrator drain timing incorrect | Add grace period + retry; fallback to manual override |
| Docker SDK permission issues (stopping containers) | Test Orchestrator permissions in isolated env first |
