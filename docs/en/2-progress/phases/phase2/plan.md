# Phase 2 — Audio/Video Translation + Web UI + GPU Control Panel

> Status: ✅ Complete | Completed: 2026-03-31
> **Index:** [← progress.md](../../progress.md) | [中文版 →](../../../../zh/2-progress/phases/phase2/plan.md)

---

## Goal

Extend the platform with:
1. **Audio/video subtitle generation and translation** — fully self-hosted, no external API calls
2. **Unified Web UI** — multi-page responsive interface accessible on phone, tablet, and PC
3. **Manual GPU control panel** — see which container owns the GPU, start/stop services manually

Auto GPU switching (Orchestrator) is deferred to Phase 3.

---

## Subtitle Strategy — Dual-Track Pipeline

Try the fastest method first; fall back to local ASR only when needed.

```
Input: video file OR YouTube URL
       ↓
[Track A] yt-dlp: attempt to fetch existing YouTube subtitles
       ↓ subtitle found → skip ASR entirely (seconds, no GPU)
       ↓ no subtitle (local file, or YouTube has none)
[Track B] ffmpeg: extract audio from video
       ↓
       Whisper STT (local GPU, faster-whisper large-v3) → transcript
       ↓
[Both tracks merge here]
       LiteLLM :4000 → Qwen 14B → translate to target language
       ↓
Output: .srt / .vtt / plain text
```

**Why this order:**
- YouTube captions (when available) are near-instant and GPU-free
- Whisper is only invoked when no pre-existing subtitle track exists
- This mirrors what Grok's web UI likely does (fetches YouTube CC, not running ASR)

---

## Architecture

```
User (browser — phone / tablet / PC)
       ↓ HTTPS / HTTP
  ai_webapp :8080  (FastAPI + HTML/CSS — responsive, mobile-first)
       ├── /             → homepage: service list + GPU status widget
       ├── /subtitle     → subtitle generation (YouTube URL or file upload)
       ├── /translate    → text translation
       ├── /gpu          → GPU control panel (manual start/stop + VRAM monitor)
       └── /status       → JSON API for GPU/container status (used by UI widgets)
       ↓
  [yt-dlp]  ←  try first for YouTube URLs
       ↓ fallback
  ai_whisper :9998  (faster-whisper, GPU)
       ↓
  ai_litellm :4000  (LiteLLM gateway → Qwen 14B)
```

All containers on `ai_paas_network`.

---

## Web UI Design Principles

- **60-point UI**: functional, not beautiful. Correctness and stability over aesthetics.
- **Responsive / mobile-first**: CSS flexbox/grid, single breakpoint at 768 px.
  - Portrait phone: stacked single-column layout
  - Tablet / desktop: two-column or sidebar layout
- **No heavy frontend framework**: plain HTML + vanilla JS + minimal CSS. Zero build step.
- **Fast to load**: no CDN dependencies for core UI (embed critical CSS inline if needed).
- **One container**: `ai_webapp` serves both the HTML pages and the backend API routes.

---

## GPU Control Panel (Step 2.6)

Exposed at `/gpu`. Capabilities:

| Feature | Implementation |
|---|---|
| Show active containers + status | `docker ps` via Docker SDK |
| Show current VRAM usage | `nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader` |
| Start / Stop individual containers | Docker SDK `container.start()` / `container.stop()` |
| One-click "switch to Visual tier" | Stops `ai_vllm` + `ai_whisper`; visual container is managed manually (Phase 2) |
| Auto-refresh every 10 s | `setInterval` JS polling `/status` endpoint |

> ⚠️ Auto tier switching (Orchestrator) is NOT in Phase 2. It is deferred to Phase 3.
> Phase 2 manual panel gives full visibility and control. Orchestrator automation builds on top of it.

---

## VRAM Budget

| Component | VRAM |
|---|---|
| vLLM (Qwen 14B, `gpu_memory_utilization=0.7`) | ~17 GB |
| Whisper large-v3 (faster-whisper) | ~3–4 GB |
| **Total** | **~20–21 GB of 24 GB** |

✅ Feasible. If memory pressure occurs: reduce `gpu_memory_utilization` to `0.6` (~14.4 GB) first.

---

## Selected Images

| Service | Image | Notes |
|---|---|---|
| Whisper | `fedirz/faster-whisper-server:latest-cuda` | OpenAI-compatible `/v1/audio/transcriptions` endpoint |
| Web App | Custom Dockerfile (Python 3.12-slim + FastAPI + yt-dlp + ffmpeg) | Built locally, stored in Harbor |

---

## Step Plan

| Step | Description | Status | Commit |
|---|---|---|---|
| **2.1** | Write Phase 2 plan (this file) | ✅ Done | `b8be598` |
| **2.2** | Add Whisper service to `docker-compose.yml`; test VRAM co-existence with vLLM | ✅ Done | `ce3095a`+pending |
| **2.3** | Add Whisper route to `litellm_config.yaml`; restart LiteLLM; verify `/v1/audio/transcriptions` | ✅ Done | this |
| **2.4** | Build Web App Dockerfile (FastAPI + yt-dlp + ffmpeg); add to `docker-compose.yml` | ✅ Done | this |
| **2.5** | Implement subtitle pipeline: yt-dlp → fallback Whisper → LiteLLM translation | ✅ Done | this |
| **2.6** | Implement GPU control panel (`/gpu` page + `/status` API + Docker SDK integration) | ✅ Done | this |
| **2.7** | Implement remaining Web UI pages: `/`, `/translate`; apply responsive CSS | ✅ Done | this |
| **2.8** | End-to-end test: YouTube URL → subtitles; local file → subtitles; GPU panel start/stop | ✅ Done | `34155de` |
| **2.9** | Update `codebase_map.md` with all new containers + endpoints | ✅ Done | this |

---

## Config Drafts (apply during Step 2.2–2.4)

**`docker-compose.yml` — Whisper addition:**
```yaml
ai_whisper:
  image: fedirz/faster-whisper-server:latest-cuda
  container_name: ai_whisper
  ports:
    - "9998:8000"
  environment:
    - WHISPER__MODEL=large-v3
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
  networks:
    - ai_paas_network
  restart: unless-stopped
```

**`docker-compose.yml` — Web App addition:**
```yaml
ai_webapp:
  build: ./services/webapp
  container_name: ai_webapp
  ports:
    - "8080:8080"
  environment:
    - LITELLM_BASE_URL=http://ai_litellm:4000/v1
    - LITELLM_API_KEY=${WEBAPP_LITELLM_KEY}
    - WHISPER_BASE_URL=http://ai_whisper:8000/v1
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro   # GPU panel needs Docker API
  networks:
    - ai_paas_network
  restart: unless-stopped
```

**`litellm_config.yaml` — Whisper route addition:**
```yaml
- model_name: whisper
  litellm_params:
    model: whisper/large-v3
    api_base: http://ai_whisper:8000/v1
```

> ⚠️ These are draft configs. Do NOT apply until Step 2.2 execution.
> Verify `fedirz/faster-whisper-server` env var names against its README before applying.

---

## Pre-Execution Checklist (resolve before Step 2.2)

- [ ] Confirm `fedirz/faster-whisper-server` GPU passthrough syntax (CUDA 12 vs 13)
- [ ] Confirm env var for model selection (may not be `WHISPER__MODEL` — check image README)
- [ ] Confirm Docker socket mount is safe (read-only `:ro` for GPU panel)
- [ ] Decide if TTS output is in scope for Phase 2 or deferred to Phase 3

---

## Risks

| Risk | Mitigation |
|---|---|
| VRAM overflow with Whisper large-v3 | Monitor `nvidia-smi` after startup; reduce to `medium` if needed |
| faster-whisper CUDA 13 compatibility unknown | Test with small model first before loading large-v3 |
| ffmpeg not in Web App container | Include explicitly in Dockerfile |
| Docker socket security (GPU panel) | Mount `:ro`; only allow start/stop of known container names (whitelist) |
| yt-dlp YouTube rate limits / format changes | Pin yt-dlp version; add graceful fallback error messages in UI |
