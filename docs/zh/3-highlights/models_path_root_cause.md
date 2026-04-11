# MODELS_PATH Root Cause Analysis & Fix

> Created: 2026-04-09 | Status: RESOLVED

## Problem

`MODELS_PATH=/Development/docker/docker-volumes/ai_paas` was set in `.env`, but Docker Compose always used the fallback value `~/ai-paas/models` (repo root's `models/` folder). This was "fixed" 5-10 times without success.

## Root Cause (First-time Diagnosis)

**Docker Compose reads `.env` from the directory where `docker-compose.yml` is located, NOT from the current working directory.**

- `.env` was at `/home/james/ai-paas/.env` (repo root)
- `docker-compose.yml` was at `/home/james/ai-paas/configs/docker-compose.yml`
- When running `docker compose -f configs/docker-compose.yml`, Compose looked for `.env` in `configs/` — found nothing — used fallback

### Evidence

```bash
# BROKEN: .env not found, fallback used
$ docker compose -f configs/docker-compose.yml config | grep source.*models
# → source: /home/james/ai-paas/models  (WRONG — fallback value)

# WORKS: explicit env-file
$ docker compose --env-file ./.env -f configs/docker-compose.yml config | grep source.*models
# → source: /Development/docker/docker-volumes/ai_paas  (CORRECT)
```

### Why Previous Fixes Failed

Every attempt modified variable names, fallback values, or shell script logic — but none addressed the fact that Docker Compose couldn't read `.env` at all. Shell scripts (using `source .env`) worked fine, masking the compose-level failure.

## Fix Applied

1. **Moved `configs/docker-compose.yml` → `docker-compose.yml`** (repo root) — Compose now finds `.env` automatically
2. **Replaced all `~/ai-paas/...` hardcoded paths** with `./relative/...` paths (11 lines)
3. **Changed fallbacks** from `~/ai-paas/models` to `./models` (safe even without `.env`)
4. **Updated `../services/...` build contexts** to `./services/...` (3 lines)
5. **Fixed `download-models.sh`** hardcoded `/home/james/ai-paas/models/comfyui` to dynamic resolution

## Verification

```bash
$ docker compose config | grep "source.*Development"
# → 3 lines with /Development/docker/docker-volumes/ai_paas ✅

$ docker compose config | grep "~/ai-paas"
# → (no output) ✅
```

## Key Lesson

When `docker-compose.yml` is not in the project root, Docker Compose's `.env` auto-discovery breaks silently. Always keep `docker-compose.yml` in the same directory as `.env`, or use `--env-file` explicitly.
