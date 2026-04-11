# Claude Code Entry Point — ai-paas

**Before writing any code or config**, read in order:

1. `docs/zh/1-for-ai/guide.md` — rules, commit format, archiving protocol, architecture facts
2. `docs/zh/1-for-ai/codebase_map.md` — full infrastructure map (do NOT scan files instead)
3. `docs/zh/2-progress/progress.md` — current phase status
4. `docs/zh/2-progress/NEED_TO_DO.md` — active task backlog

Do not scan `models/`, `xinference_models/`, or `litellm_data/`. Trust the docs as ground truth.

---

## ⛔ Hard Rules (non-negotiable)

- All config, comments, commit messages: **English**
- Communicate with human: **Chinese**
- **End every response with AskUserQuestion**: After completing a task, answering a question, or providing any information — always end by using the `AskUserQuestion` tool to ask the user what they'd like to do next. Never finish a response with plain text only.
- Read `NEED_TO_DO.md` at start; ask user if they want you to re-read it before starting

---

## Commands

```bash
docker ps && nvidia-smi                      # Container + GPU status
docker logs -f ai_litellm                    # LiteLLM logs
cd /home/james/ai-paas && docker compose up -d
docker compose restart ai_litellm

curl -X POST "http://192.168.0.19:4000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"hello"}],"max_tokens":10}'
```

---

## Documentation Map

| Need | File |
|---|---|
| Working rules + commit format + archiving | `docs/zh/1-for-ai/guide.md` |
| Infrastructure map (containers, APIs, VRAM) | `docs/zh/1-for-ai/codebase_map.md` |
| Phase progress + roadmap | `docs/zh/2-progress/progress.md` |
| Active task backlog | `docs/zh/2-progress/NEED_TO_DO.md` |
| Architecture decisions | `docs/zh/3-highlights/architecture_vision.md` |
| Failed approaches | `docs/zh/3-highlights/archived/` |
| New member setup | `docs/zh/4-for-beginner/quick_start.md` |
