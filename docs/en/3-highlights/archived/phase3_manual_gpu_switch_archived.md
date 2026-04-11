# Phase 3 — Manual GPU Time-Sharing Architecture (Archived)

> **Archived:** 2026-04-05
> **Reason:** Phase 3's time-sharing (手动时分调度) approach was superseded by Phase 4's GPU Router architecture. The old design relied on manual switching and a bolted-on Orchestrator layer. Phase 4 replaces this with an independent FastAPI + Celery + Redis router that owns the API gateway role AND GPU scheduling natively, eliminating LiteLLM. See `../../../zh/2-progress/phases/phase4/plan.md`.

---

## Original Architecture (Archived)

```
                    ┌─────────────────────────────────────┐
                    │      ai-paas Orchestrator           │
                    └──────┬──────────────┬───────────────┘
              ┌────────────┘              └────────────┐
              ▼  Text/Voice Layer                     ▼  Visual Layer
              LiteLLM :4000 → vLLM/Whisper            ComfyUI (exclusive)
              VRAM: ~21 GB                            VRAM: up to 24 GB
```

## Key Decisions (Superseded by Phase 4)

| Decision | Old (Phase 3) | New (Phase 4) |
|---|---|---|
| API Gateway | LiteLLM persists | GPU Router owns :4001 → :4000 |
| Orchestrator | Bolted onto webapp | Independent FastAPI service |
| Task Queue | In-memory or simple Redis | Celery + Redis with Flower |
| Scope | Only vLLM ↔ ComfyUI switching | All GPU services with extensible provider interface |
| Backend | Hardcoded routes | Abstract `BackendProvider` interface |
