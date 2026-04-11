# ai-paas — Documentation System Reference

> **What is this file:** After-action review of the documentation system built for this project.
> Serves as both a reference for *why* each file exists and a template that could be adapted
> for other projects.
>
> Last updated: 2026-04-05 (rebuild to match current docs state: 32B upgrade, /models UI, Phase 3 infra)
>
> **Related:** [中文版 →](../../zh/1-for-ai/ai_docs_system_template.md)

---

## Why this system exists

When an AI agent starts a session it normally does one of two things:

| Without this system | With this system |
|---|---|
| Reads 50–200 source files to understand the project | Reads 3–4 doc files, then writes code |
| Spends 40–60% of token budget just *understanding* | Spends > 90% of tokens on the actual task |
| Invents patterns that conflict with existing ones | Follows the project's own patterns |
| Forgets conventions across sessions | Re-reads the same docs every session in seconds |

**The key insight:** the AI does not need to read code to understand structure —
it needs a well-maintained human-readable map.

Startup cost: ~2,000–4,000 tokens.
Savings per session: 20,000–80,000 tokens (eliminates source-code scanning).
ROI is positive after the very first task.

---

## The file set (as actually deployed)

```
/home/james/ai-paas/
├── CLAUDE.md                             ← Auto-injected every turn (Claude Code entry point)
├── docker-compose.yml                    ← Primary config: all containers
├── litellm_config.yaml                   ← Model routing + aliases
├── .env / .env.example                   ← Secrets + template
├── gpu-switch.sh                         ← CLI: switch VRAM tier (text ↔ visual)
└── docs/
    ├── en/                               ← English (AI-authoritative)
    │   ├── 00_INDEX.md                   ←   Master navigation hub
    │   ├── 1-for-ai/
    │   │   ├── guide.md                  ←   ⭐ Rules, commit format, workflow, architecture facts
    │   │   ├── codebase_map.md           ←   ⭐ Infrastructure map (replaces source scanning)
    │   │   └── ai_docs_system_template.md ←   This file — docs system reference
    │   ├── 2-progress/
    │   │   ├── progress.md               ←   ⭐ Phase index with commit hashes
    │   │   └── phases/
    │   │       ├── phase1/plan.md        ←   Phase 1: vLLM + LiteLLM (✅ complete)
    │   │       ├── phase2/plan.md        ←   Phase 2: Whisper + webapp (⏳ pending)
    │   │       └── phase3/plan.md        ←   Phase 3: ComfyUI + VRAM switching (🔄 in progress)
    │   ├── 3-highlights/
    │   │   ├── architecture_vision.md    ←   Strategic design decisions + rationale
    │   │   └── archived/                 ←   Superseded docs — kept for context, never deleted
    │   └── 4-for-beginner/
    │       └── quick_start.md            ←   Environment setup + first run walkthrough
    └── zh/                               ← Chinese (translation + active backlog)
        ├── 00_INDEX.md
        ├── README.md
        ├── 1-for-ai/
        │   └── guide.md                  ←   Chinese agent guide (mirrors EN)
        ├── 2-progress/
        │   ├── progress.md               ←   Chinese progress index
        │   ├── NEED_TO_DO.md             ←   ⭐ Active task backlog (only pending items)
        │   ├── task-logs/                ←   Archived completed NEED_TO_DO files
        │   └── phases/                   ←   Chinese phase plans
        └── 3-highlights/
```

**Read frequency:**

| File | When read | Purpose |
|---|---|---|
| `CLAUDE.md` | Every turn (auto-injected) | Session entry — must stay under 80 lines |
| `guide.md` | Once per session | Rules + facts + commit format |
| `codebase_map.md` | Once per session | Infrastructure reference |
| `progress.md` | Once per session | Current phase context |
| `NEED_TO_DO.md` | When working on bugs/tasks | Active backlog (zh only) |
| `00_INDEX.md` | When navigating | Master directory of all docs |
| Phase plans | When working on a phase | Detailed step logs + decisions |
| Architecture vision / deep docs | Only when the task needs it | Strategy + rationale |

---

## File-by-file purpose and design

### `CLAUDE.md` — Session Entry Point

Auto-injected by Claude Code on every turn. Kept under 80 lines to avoid context waste.
Four sections only:

1. **Session Start Protocol** — ordered reading list, explicit "do NOT scan models/ or data/"
2. **Hard Rules** — language, communication, AskUserQuestion requirement
3. **Commands** — key CLI shorthands
4. **Documentation Map** — one-line table mapping need → file

Points to `docs/zh/1-for-ai/guide.md` and `docs/zh/1-for-ai/codebase_map.md` as primary
reading (Chinese version is currently more up-to-date with live work).

### `1-for-ai/guide.md` — Working Rules

Read every session before touching config or code. Contains:

1. **Reading Order** — what to read after this file
2. **Non-negotiable rules** — language, commits, doc trust, NEED_TO_DO archiving protocol
3. **Work Transparency** — mandatory human-readable explanations for every non-trivial action
4. **Commit message format** — conventional commits with real project examples
5. **How to handle requests** — deploy new service / bug / model change / refactor workflows
6. **Common pitfalls** — project-specific wrong patterns (10 items)
7. **Key architecture facts** — 9 facts the agent must never violate
8. **Development commands** — duplicate of CLAUDE.md commands (intentional redundancy)

Key design decision: the NEED_TO.do archiving rule lives here (not in NEED_TO_DO.md itself)
because the backlog file changes constantly — rules must live in always-read docs.

### `1-for-ai/codebase_map.md` — Infrastructure Map

The most important file. Replaces source-code scanning. Contains:

1. **Warning header** with maintenance rule (update this file when you modify listed files)
2. **Repository root ASCII tree** — full layout in one glance
3. **File-by-file reference** — every non-trivial file with function, key variables, and patterns
4. **Active containers table** — image, port, status, purpose
5. **API endpoints** — production, webapp, Whisper, ComfyUI, OpenClaw, debug
6. **GPU / VRAM map** — resource consumption per scenario
7. **Host network details** — IPs, URLs
8. **Key architectural patterns** — 6 numbered patterns

Current as of 2026-04-02: 5 containers documented (vLLM, LiteLLM, PostgreSQL, Whisper, webapp, ComfyUI).
Last major update: disk cleanup (+20 GB freed), 32B/72B upgrade research, model table updated.

### `2-progress/progress.md` — Phase Index

Navigation-only file. Each phase has a separate plan with full step logs.

Current status:
- **Phase 1** (Compute Hub: vLLM + LiteLLM) — ✅ Complete — 6 steps, 6 commits
- **Phase 2** (Audio/Video: Whisper + Web UI) — ✅ Complete — 9 steps
- **Phase 3** (Visual: ComfyUI + VRAM switching) — 🔄 In Progress — Step 3.3 infra done

Contains commit hash tables so agents don't need to run `git log`.

### `2-progress/NEED_TO_DO.md` — Living Backlog (zh only)

Plain checkbox list. Read at session start. Conventions:

- Newest date group at top
- Only pending (`[ ]`) items in the active file
- When all items in a date group are done → archive to `task-logs/NEED_TO_DO_ARCHIVED_<MonthDay.Year>.md`
- Archiving rule is in `guide.md` Section 2, not here

### `3-highlights/architecture_vision.md` — Strategic Context

Why the project is built this way. Contains:

- Four use cases: OpenClaw agent, subtitle/translate, AI video, digital human
- Time-division VRAM scheduling vision (not static partitioning)
- Why each architecture choice was made (vLLM over Xinference, LiteLLM as gateway, PostgreSQL over SQLite, etc.)
- Three-layer architecture diagram (Applications → Inference → Infrastructure)
- Nine guiding principles

### `4-for-beginner/quick_start.md` — Onboarding

Prerequisites, system state check, stack start, key URLs, API key issuance,
model addition, common first-time errors — all in one file.

---

## Design patterns embedded in this docs system

| Pattern | What it does | Where applied |
|---|---|---|
| **Ordered reading** | Agent reads specific files in order before coding | CLAUDE.md → guide.md → codebase_map.md → progress.md |
| **Maintenance rule** | Agent must update docs when it modifies code | Embedded in codebase_map header + guide.md |
| **Bilingual authoritative** | EN docs are AI-authoritative; ZH is working language | Cross-linked with `**Related:**` lines |
| **NEED_TO_DO pointer** | Rule lives in guide.md, backlog is scratchpad only | First line of NEED_TO_DO.md points to guide.md |
| **Archive, never delete** | Superseded docs move to `archived/` with a note | `3-highlights/archived/` convention |
| **Command duplication** | Same commands in CLAUDE.md and guide.md | Intentional — agent always has them regardless of which file it's reading |
| **Commit hash tables** | progress.md records commits so agents skip `git log` | Phase commit tables in progress.md |
| **Under 80 lines** | Entry-point file stays short to save context budget | CLAUDE.md discipline |
| **Work transparency** | Agent explains decisions in plain language before acting | guide.md Section 2 — mandatory 技术调研日志 in phase plans |

---

## Injecting this system into a new project — checklist

```
[ ] Entry-point file at repo root (CLAUDE.md / .windsurfrules / .clinerules / etc.)
      - Session start protocol with real file paths
      - Explicit "Do not scan <source-dir>/" with actual directories
      - "Trust the docs" instruction
      - Key CLI commands from this project
      - Documentation Map table
      - Keep under 80 lines

[ ] docs/<lang>/00_INDEX.md
      - Four sections: 1-for-ai / 2-progress / 3-highlights / 4-for-beginner
      - One row per file, relative link, one-line purpose

[ ] docs/en/1-for-ai/guide.md
      - Reading Order section
      - Non-negotiable rules (language + trust-docs + commits + docs maintenance)
      - Commit format with real examples from this project
      - Request handling: deploy / bug / model-change / refactor
      - Common pitfalls (at least 5, project-specific)
      - Key architecture facts (5–10, the things agents get wrong most)
      - Dev commands (duplicate of entry-point file)

[ ] docs/en/1-for-ai/codebase_map.md
      - Warning header with maintenance rule embedded at top
      - "Last updated: <date> (<reason>)" line
      - Full ASCII tree of repo root
      - Every non-trivial file: path + function + key variables/patterns
      - Active containers + API endpoints + VRAM map
      - Architectural patterns section at the end

[ ] docs/en/2-progress/progress.md
      - Overall status table (all phases, emoji status)
      - "Currently active: Phase X.Y" line
      - Detail for each phase with commit hashes

[ ] docs/<lang>/2-progress/NEED_TO_DO.md
      - Pointer line at top ("archiving rule is in guide.md Section 2")
      - At least one date group with checkbox items
      - Newest at top; pending items only
      - task-logs/ subdirectory for archiving

[ ] docs/en/3-highlights/architecture_vision.md
      - Why the project is built this way
      - Key design decisions with rationale

[ ] docs/en/4-for-beginner/quick_start.md
      - Prerequisites table
      - First build / run walkthrough
      - Common first-time errors and fixes

[ ] Cross-link EN and ZH versions with "**Related:**" lines
```

---

## Common mistakes when setting up this system

| ❌ Mistake | ✅ Correct approach |
|---|---|
| Entry-point file over 100 lines | Keep under 80; move all detail to guide.md |
| codebase_map entries are one sentence: "Contains API views" | Include function names, key params, auth requirements |
| `Last updated` date with no reason | Always add reason: `(added X, updated Y to Z)` |
| Deleting superseded design docs | Move to `3-highlights/archived/` with a note |
| Putting domain rules directly in codebase_map | Create a separate `1-for-ai/<domain>.md` when > 30 lines |
| Only adding maintenance rule to guide.md | Embed it in codebase_map header too — that's where agents read it last |
| Telling agent "don't scan src/" | Tell agent the exact path: "don't scan `models/` or `data/`" |
| No "trust the docs" instruction | Add explicit rule: "treat docs as ground truth; no full scan unless conflict" |
| progress.md lists only future phases | Include completed phases with commit hashes — history prevents repetition |
| Putting hard rules only in NEED_TO_DO.md | Put rules in guide.md; put only a pointer in NEED_TO_DO.md |
| NEED_TO_DO.md grows indefinitely | Archive completed sessions to task-logs/; keep active file to pending items only |
| Bilingual: CN overwrites EN codebase_map | EN is authoritative for AI-facing docs; CN is translation + working scratchpad |
| Agent ends session with plain text "Done!" | Require AskUserQuestion as hard rule in guide.md Section 2 |
