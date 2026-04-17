- **归档规则在 guide.md Section 2，不在此处** — 请读 `docs/en/1-for-ai/guide.md` ← 始终保留这行
- **归档操作**：将已完成的 items 按日期归档到 `docs/zh/2-progress/task-logs/NEED_TO_DO_ARCHIVED_YYYY-MM-DD.md`。每次 append 到最后，当日完成当日归档。
- **在此文档中的 items 都是未完成的**。
- **每次开始工作前先读取此文件**，了解当前待办状态。

> PKB目录如下：
> /Development/docker/docker-volumes/syncthing-docker/ObsidianVault/PARA-Vault/2_AREA/10-Area-Artificial_Intelligence/Project_AI_Marketing_Personal
> 1. 一切工作进度以PKB为准
> 2. 每次完成单元工作，就需要同步git/pkb
---

### 长期目标

- **MCP/Skills 集成**：将 MCP server 对接到 vLLM 的 tool calling 能力（`--enable-auto-tool-choice --tool-call-parser hermes`），使 OpenClaw 能使用外部工具

### 待解决问题

- **yt-dlp cookies 续期** ✅ 已实现并部署验证：`ai_cookie_manager` sidecar 容器（Playwright + noVNC），自动每 6 小时刷新。容器运行中，已自动刷新 2 次，health API 返回 healthy。
  - 启动：`docker compose --profile cookies up -d`
  - 首次登录：`http://localhost:6901`（noVNC → YouTube 登录）
  - 健康检查：`curl http://localhost:6902/health`

### 多模型支持后续

- [ ] Gemma 4 26B A4B AWQ 量化：对 `/models/gemma-4-26B-A4B/`（BF16 ~50GB）做 AWQ 4-bit 量化，输出到 `/models/gemma-4-26B-A4B-awq/`，然后创建 vllm-gemma 容器并测试切换

---

### Phase 4 补完

（无 — Phase 4 补完已完成并归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-07.md`）

（2026-04-09 全链路修复已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-09.md`）

（2026-04-09 MODELS_PATH 根因修复 + 硬编码路径清理已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-09.md`）

（2026-04-12 release-please + license header + comfyUI 工作流浏览器等已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-13.md`）

（2026-04-13 ComfyUI 工作流导入修复 + 内置工作流原生浏览已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-13.md`）

### paas-controller.sh 改进

（2026-04-13 `prepare` 下载 UX 全面改进已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-13.md`）

（2026-04-13 CogVideoX latent_rgb_factors_reshape 修复已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-13.md`）


- [ ] 下载有问题 ✅ 已修复：下载完成检测逻辑（`api_download`）只列新增文件，不再误报已有文件；TrueNAS NFS Maproot User=root 修复目录写权限（tv/movies/music/files 不再显示🔒）。详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-15.md`。

- [ ] 扩充 /download 页面功能（2026-04-17 提出）：
  - 支持任意 URL 视频平台（yt-dlp 已支持 1000+ 站点含 YouTube/B站/Twitter/Instagram/Facebook 等）
  - 视频下载：可选格式后缀（mp4/mkv/webm）、分辨率、是否嵌入字幕（无字幕时自动 Whisper 生成）
  - 音频下载：可选后缀（mp3/m4a/flac/opus/wav）
  - 字幕单独下载：可选语言、可选 AI 翻译
  - 批量下载：支持播放列表 URL