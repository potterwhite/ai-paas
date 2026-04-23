# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Claude Code Entry Point — ai-paas

Read before touching anything: `docs/zh/1-for-ai/guide.md` → `codebase_map.md` → `progress.md` → `NEED_TO_DO.md`

---

## Rules

- Config / comments / commits: **English** · Human comms: **Chinese**
- Always end response with `AskUserQuestion` tool
- Never scan `models/`, `xinference_models/`, `litellm_data/`

---

## Commands

```bash
docker ps && nvidia-smi
docker logs -f ai_webapp | ai_router | ai_vllm_qwen
docker compose build webapp && docker compose up -d webapp
docker compose up -d
docker compose restart ai_router

# Switch vLLM model profile (only one at a time)
docker compose --profile llm-qwen up -d vllm-qwen

# Test
curl -X POST http://192.168.0.19:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-1234" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
curl http://192.168.0.19:4000/v1/health
```

---

## Docs & PKB

| Need | Path |
|---|---|
| Rules + commit format | `docs/zh/1-for-ai/guide.md` |
| Infrastructure map | `docs/zh/1-for-ai/codebase_map.md` |
| Active tasks | `docs/zh/2-progress/NEED_TO_DO.md` |
| PKB deploy logs | `/Development/docker/docker-volumes/syncthing-docker/ObsidianVault/PARA-Vault/2_AREA/10-Area-Artificial_Intelligence/Project_AI_Marketing_Personal/deploy/` |
