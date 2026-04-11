# ai-paas — AI Agent Guide

> **Target audience:** AI coding agents (Claude Code, Cursor, Windsurf, Copilot, etc.)
> **Read this before touching any config or code.**
> **Related:** [中文版 →](../../zh/1-for-ai/guide.md)

---

## 1. Reading Order (every session)

1. **This file** — understand how to work in this repo
2. **[`codebase_map.md`](codebase_map.md)** — full infrastructure map (replaces directory scanning)
3. **[`../2-progress/progress.md`](../2-progress/progress.md)** — current phase + active tasks
4. **[`../../zh/2-progress/NEED_TO_DO.md`](../../zh/2-progress/NEED_TO_DO.md)** — active task backlog (when working on bugs/tasks)
5. **Relevant reference doc** — only if your task requires it (API spec, etc.)

---

## 2. Non-Negotiable Rules

### Code & Config
- All config files, comments, and commit messages must be in **English**
- Communicate with the human in **Chinese**
- After EVERY task (code, docs, research, commit): use the `AskUserQuestion` tool as the final step — never end with plain text. This is a hard constraint, not a suggestion.

### NEED_TO_DO.md Protocol (run this at the start of every session)
1. Read `docs/zh/2-progress/NEED_TO_DO.md`
2. Ask the user: "是否需要我重新读一下 NEED_TO_DO.md 再开始？" — they update it frequently
3. Work through unchecked items; check off `[x]` when done
4. When ALL items in a date group are `[x]`, **archive** the file:
   - Copy the completed items to `docs/zh/2-progress/task-logs/NEED_TO_DO_ARCHIVED_<MonthDay.Year>.md`
   - Remove the archived date group from `NEED_TO_DO.md`
   - Keep `NEED_TO_DO.md` short (active items only)
5. This archiving rule is here (not in `NEED_TO_DO.md` itself) because the backlog file changes constantly — rules must live in always-read docs

### Work Transparency — MANDATORY (人类可读性要求)

The human owner of this repo **cannot read your mind**. Every non-trivial action must be explained in plain Chinese before or as it happens. This is not optional courtesy — it is a hard rule.

**What to explain, always:**
- Before any web search or external lookup: "我要去查 X，因为 Y"
- When you discover something unexpected (repo renamed, env var wrong, image deprecated): immediately document it in the relevant ZH plan file under a `## 🔍 技术调研日志` section
- When you choose between options: state what the options are and why you picked one
- When a step takes longer than expected: explain what is happening ("镜像体积大，pull 中，预计 N 分钟")
- When something fails: state the failure reason in plain language before trying the fix

**Where to write it:**
- Real-time (inline in chat): brief 1–2 sentence explanation of what you are about to do
- Persistent (in docs): write findings into `docs/zh/2-progress/phases/phaseN/plan.md` under `## 🔍 技术调研日志`
  - This section is mandatory whenever you do external research (web fetch, image investigation, etc.)
  - It records: what you searched, what you found, what changed from the original plan, what you decided

**Format for the 技术调研日志 section:**
```
## 🔍 技术调研日志（AI 执行思路记录）

> 这一节专门给人类看。记录 AI 每一步的决策依据、搜索过程、发现了什么、为什么这样选。

### <Step X.Y 名称>（<日期>）

**出发点：** ...

**发现 1：** ...（原计划写的 X，实际是 Y，原因是 Z）

**决策：** ...

**当前状态：**
- [x] 已完成的子步骤
- [ ] 尚未完成的子步骤
```

### Commits
- **One commit per logical unit** — do not accumulate changes and commit at the end
- Follow the commit message format below exactly
- Never commit broken configs

### Documentation
- After modifying any file listed in `codebase_map.md`, update that file in the same commit
- When a Phase step is completed, update the status in `progress.md`

### Infrastructure Constraints — CRITICAL
- **Everything runs as Docker containers only** — no bare-metal services
- **Single RTX 3090 = 24 GB VRAM** — only one heavy model loaded at a time
- **vLLM and ComfyUI cannot run simultaneously** — VRAM switching required
- **Never change `gpu_memory_utilization` without updating HANDOFF-equivalent docs**

---

## 3. Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

**Type** (required): `feat` · `fix` · `docs` · `refactor` · `perf` · `test` · `build` · `chore`

**Subject** (required): English, ≤70 chars, present tense, no leading capital
- ✅ `fix: increase gpu_memory_utilization to 0.7 for 16k context support`
- ✅ `feat: add whisper-faster service to docker-compose`
- ❌ `Updated stuff and fixed things`

**Body** (recommended): bullet points explaining what and why

**Footer** (recommended): `Phase X.Y Step Z complete.`

---

## 4. How to Handle Human Requests

### "Deploy a new service"
1. Ask clarifying questions (which container image, port, VRAM impact)
2. Write a plan in `docs/` — **no config changes yet**
3. Wait for approval
4. Implement step by step, one commit per step

### "There's a bug / service is down"
1. Run `docker ps` to see container states
2. Run `docker logs <container>` to get the error
3. Fix it; document root cause if non-trivial
4. Commit with `fix:` prefix

### "Change model or scale"
1. Check current VRAM budget in `codebase_map.md`
2. Verify the change does not exceed 24 GB total
3. Update `docker-compose.yml` and `litellm_config.yaml` in the same commit
4. Update `codebase_map.md` in the same commit

### "Refactor / reorganize something"
1. Write a refactor plan in `docs/en/3-highlights/`
2. Wait for approval
3. Execute step by step

---

## 5. Common Pitfalls

| ❌ Wrong | ✅ Right |
|---|---|
| Start vLLM and ComfyUI at the same time | Always stop vLLM before starting ComfyUI (VRAM exclusive) |
| Hardcode model path in code | Use the mount path `/models/<model-dir>` as defined in compose |
| Use `sk-1234` master key in apps | Issue a dedicated virtual key per app via LiteLLM `/key/generate` |
| Edit 3 files then do one big commit | Commit after each logical step |
| Start work without reading codebase_map | Read codebase_map first |
| Edit config, forget to update codebase_map | Always sync codebase_map in same commit |
| Try to use Xinference | It is permanently abandoned — do not retry (CUDA spawn bug) |
| Set `gpu_memory_utilization` > 0.7 during vLLM+Whisper co-run | Max 0.7 for vLLM; Whisper needs ~4 GB headroom |
| Call vLLM directly from apps | Always route through LiteLLM (:4000); vLLM (:9997) is debug-only |

---

## 6. Key Architecture Facts

- **API Gateway:** All currently route through LiteLLM (:4000). Phase 4.5 will replace LiteLLM with ai_router (:4000). vLLM (:9997) is debug-only.
- **Model alias `qwen` maps to the 14B AWQ model** — apps reference `"model": "qwen"` not the full path
- **OpenClaw must use model string `qwen`** — `litellm/qwen` returns 400 in LiteLLM 1.82.1+; verified 2026-03-28
- **Tool calls require `--enable-auto-tool-choice --tool-call-parser hermes`** — already set in compose; removing them breaks OpenClaw agent loops
- **VRAM budget: 0.7 × 24 GB ≈ 17 GB for vLLM** — leaves ~7 GB for co-running Whisper (Phase 2)
- **Planned upgrade: Qwen2.5-32B-Instruct-AWQ** — requires `gpu_memory_utilization=0.95`, ~20-21 GB VRAM; cannot co-run with Whisper; 72B tested and rejected (0.5-2 tok/s with cpu-offload — too slow)
- **Containers live on `ai_paas_network`** — inter-container hostnames match `container_name` values (e.g. `ai_vllm`, `ai_litellm_db`)
- **PostgreSQL is required for LiteLLM** — `DATABASE_URL=sqlite://...` fails (Prisma ORM rejects it)
- **Three failed Xinference attempts are preserved in `archived/`** — do not repeat any of those approaches

---

## 7. Development Commands

```bash
# Check running containers and health
docker ps

# Tail logs for a service
docker logs -f ai_vllm
docker logs -f ai_litellm

# GPU utilization and VRAM
nvidia-smi

# Restart the full stack
cd /home/james/ai-paas && docker compose down && docker compose up -d

# Restart a single service
docker compose restart ai_litellm

# Test LiteLLM gateway (app-facing)
curl -X POST "http://192.168.0.19:4000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"hello"}],"max_tokens":20}'

# Test vLLM directly (debug only)
curl -X POST "http://192.168.0.19:9997/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"/models/qwen2.5-14b-instruct-awq","messages":[{"role":"user","content":"hello"}],"max_tokens":20}'

# List LiteLLM virtual keys (admin)
curl "http://192.168.0.19:4000/key/list" -H "Authorization: Bearer sk-1234"

# Issue a new virtual key for an app
curl -X POST "http://192.168.0.19:4000/key/generate" \
  -H "Authorization: Bearer sk-1234" \
  -H "Content-Type: application/json" \
  -d '{"key_alias":"app-name","models":["qwen"],"duration":null}'
```
