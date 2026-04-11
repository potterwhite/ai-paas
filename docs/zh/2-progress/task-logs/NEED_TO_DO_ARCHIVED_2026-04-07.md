# Archived 2026-04-07

## Completed items (from NEED_TO_DO.md "Phase 4 补完" section)

- [x] 为什么我 http://192.168.0.19:8888/models 这里搜索 "gemma" 却没东西出现。
  - **Root cause**: `sort=trending` is not a valid HuggingFace API sort parameter; HF returns `{"error": "..."}` dict instead of array. Frontend JS renders dict as empty result.
  - **Fix**: Map unknown sort values to "downloads". Validate response is array before returning to client.
  - **Commit**: `8a78ce7` — fix: HuggingFace search fails with sort=trending
- [x] 我希望自动开关container做得更好：例如我用了文生图，但是此刻后台的comfyUI的container是exited,系统要给提醒"容器xxx当前尚未打开，需要打开？"如果点yes，就自动后台切换，给一个widget,告诉user,正在后台打开requirement container.
  - **Fix**: /comfyui page now detects container status, shows prompt widget if not running, auto-stops vLLM (VRAM conflict), starts ComfyUI with progress bar.
  - **Commit**: `dda1313` — feat: ComfyUI auto-start prompt + loading widget
- [x] 每一个功能都是做完就git commit
  - All items above committed as part of this session.

## Additional fixes (not from NEED_TO_DO but completed today)

- [x] ComfyUI auto-starts with `docker compose up -d` even though it shouldn't
  - **Root cause**: `restart: "no"` only prevents auto-restart, not initial creation by `up -d`.
  - **Fix**: Added `profiles: ["comfyui"]` to ComfyUI service.
  - **Commit**: `1a29b4c` — fix: ComfyUI excluded from default `docker compose up -d` via profiles
- [x] Router API prefix mismatch
  - **Root cause**: Routes registered at `/api/v1/` but WebApp `LITELLM_BASE_URL` expects `/v1/`.
  - **Fix**: Changed all `app.include_router` prefixes from `/api/v1` to `/v1`.
  - **Commit**: `70564b9` — fix: Router API prefix `/api/v1` → `/v1` for OpenAI compatibility

## Second pass — additional items completed after re-reading NEED_TO_DO.md

- [x] 以后每次在 ask user question 工具界面都给"重新检查 NEED_TO_DO.md"选项
  - **Fix**: Saved to memory system for persistent behavior.
- [x] 控制台 ComfyUI 生图
  - **Done**: Downloaded SD1.5 checkpoint, submitted workflow via API, generated `comfyui_test_00001_.png` (398KB). Image at `data/comfyui_workdir/output/` and viewable at `http://192.168.0.19:8188/view?filename=comfyui_test_00001_.png&type=output`.
- [x] /models 搜索仍然无结果
  - **Root cause**: Browser caching old JS with broken `sort=trending`. Backend API always worked.
  - **Fix**: Added `Cache-Control: no-cache` middleware to all HTML pages.
  - **Commit**: `029aa02` — fix: add no-cache headers to HTML pages
- [x] ComfyUI RuntimeError: Could not detect model type
  - **Root cause**: Previously downloaded diffusers-format model (`stable-diffusion-v1-5/text_encoder/model.fp16.safetensors`) showed up in checkpoint dropdown and was incorrectly selected.
  - **Fix**: Removed `checkpoints/stable-diffusion-v1-5/` directory, keeping only proper `*-pruned-emaonly.safetensors` checkpoint.
- [x] 生完图在哪里看
  - **Answer**: `data/comfyui_workdir/output/` on host, or via `http://192.168.0.19:8188/view?filename=XXX&type=output`.
  - **Commit**: `5fe01eb` — feat: add workflow guide + image output info to /comfyui page
- [x] 如何获取工作流给 ComfyUI
  - **Fix**: Two new cards added to /comfyui: (1) "如何获取工作流" listing ComfyWorkflows.com, OpenComfy.io, Reddit, YouTube sources + import/export instructions; (2) "生成的图片或视频在哪里看" with 3 viewing methods.
- [x] 为什么不 archive 完成的 items
  - **Fix**: Now archiving immediately after completion. This item and the workflow/info guide above are included in the same archive file.

## Current NEED_TO_DO.md state

Items still pending:
- yt-dlp cookies 续期
- LiteLLM 数据库数据迁移
- MCP/Skills 集成长期目标

---

# Archived 2026-04-07 (second pass — ComfyUI workflows + model path config)

- [x] 有没有办法附带一些工作流在docker内部，方便一上来就能够用。数字人也是用comfyUI吗？如果是就至少每种应用（图/视频/数字人）有1条工作流。如果可以有很不同的体验，那就至少2条。
  - **Solution**: 6 production-ready workflow JSONs in `data/comfyui_workflows/` (git-tracked):
    - `01_image_sd15_txt2img.json` — SD 1.5 text→image (512×512)
    - `02_image_sdxl_txt2img.json` — SDXL 1.0 text→image (1024×1024)
    - `03_video_cogvideox_t2v.json` — CogVideoX-5B text→video
    - `04_video_cogvideox_i2v.json` — CogVideoX-5B image→video
    - `05_digital_human_liveportrait_drive.json` — LivePortrait video drive
    - `06_digital_human_liveportrait_expression.json` — LivePortrait expression editor (sliders)
  - All workflows use **local model paths** (no runtime HuggingFace downloads).
  - Auto-setup via `services/comfyui/pre-start.sh` → `setup.sh` runs on container startup.

- [x] 我需要增加一个配置，配置模型文件存储的位置（绝对路径），目前想到最好的办法（如果有更好办法可以改）是写到.env文件里。
  - **Solution**: Added `MODELS_PATH` to `.env` / `.env.example`. All services (vLLM, router, ComfyUI) now use `${MODELS_PATH:-~/ai-paas/models}` in docker-compose.yml volume mounts.
  - ComfyUI specifically mounts `${MODELS_PATH}/comfyui` → `/root/ComfyUI/models`.
  - Default value falls back to original path so existing setups are unaffected.

- [x] Auto-rebuild: `git clone` → `docker compose up` → fully working (zero manual steps)
  - **Solution**: `services/comfyui/setup.sh` (idempotent, git-tracked) covers: node install (Manager, CogVideoXWrapper, VideoHelperSuite, AdvancedLivePortrait) + all model downloads (CogVideoX-5B ~21GB, LivePortrait ~350MB, SD 1.5 ~4GB, SDXL ~7GB).
  - `services/comfyui/user-scripts/pre-start.sh` (git-tracked) hooks into yanwk image's pre-start mechanism. Runs setup.sh before ComfyUI starts.
  - Both scripts are bind-mounted as `:ro` inside the container.

