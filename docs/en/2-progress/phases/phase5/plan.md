# Phase 5 — SynapseERP + ai-paas Integration (Agent-First ERP)

> **Status:** Design notes only, implementation TBD
> **中文文档 →** [中文文档 →](../../../zh/2-progress/phases/phase5/plan.md)

---

## Vision

ai-paas and SynapseERP are not two independent systems — they are **infrastructure vs business layers**.

### Layered Architecture

```
┌──────────────────────────────────────────┐
│          SynapseERP (Business Layer)      │
│                                          │
│  synapse_pm        · Project Mgmt         │
│  synapse_attendance · Attendance          │
│  synapse_ai_inference · LLM Inference     │
│  synapse_ai_audio   · Audio Processing    │
│  synapse_ai_visual  · Visual Generation   │
└──────────────────┬───────────────────────┘
                   │  API calls (ai-paas /api/v1/*)
┌──────────────────▼───────────────────────┐
│          ai-paas (Infrastructure Layer)   │
│                                          │
│  ai_router — Unified API + GPU scheduler  │
│  vLLM / Whisper / ComfyUI — GPU nodes    │
│  Redis + Celery — Task queue             │
└──────────────────────────────────────────┘
```

### ai-paas Provides
- GPU compute (vLLM inference, speech transcription, visual generation)
- Unified API entry (ai_router:4000)
- Exclusive GPU scheduling
- API Key management (scoped keys per app/user)

### SynapseERP Does
- User-facing AI feature entry (submit tasks, view results, link to projects)
- Agent-First interfaces (complete REST API + structured docs for AI consumption)
- Rules engine + approval workflow
- Event system (publish/subscribe business events)

---

## Agent-First ERP Design Principles

1. **API before UI** — Every feature has a REST endpoint, fully usable without frontend
2. **Structured documentation** — AI knows "what data exists, how to query/modify" without scanning code
3. **Event-driven** — System pushes events to agents, not humans checking reports
4. **Rules + Approval** — Humans define rules, agents execute, humans approve exceptions
5. **Semantic layer** — Data models carry business-meaning tags

**Development order is opposite to traditional ERP:**
Traditional: UI first → API later
Agent-First: API + data model + events → UI last

---

## Dependencies

- Phase 4 (ai-paas GPU Router) must complete first
- SynapseERP needs expanded API coverage and Agent-Readable documentation
