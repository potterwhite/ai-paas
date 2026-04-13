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

- **yt-dlp cookies 续期**：设计 server 端自动化从浏览器提取和更新 cookies 的机制，不依赖手动导出

### 多模型支持后续

- [ ] Gemma 4 26B A4B AWQ 量化：对 `/models/gemma-4-26B-A4B/`（BF16 ~50GB）做 AWQ 4-bit 量化，输出到 `/models/gemma-4-26B-A4B-awq/`，然后创建 vllm-gemma 容器并测试切换

---

### Phase 4 补完

（无 — Phase 4 补完已完成并归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-07.md`）

（2026-04-09 全链路修复已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-09.md`）

（2026-04-09 MODELS_PATH 根因修复 + 硬编码路径清理已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-09.md`）

（2026-04-12 release-please + license header + comfyUI 工作流浏览器等已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-13.md`）

✅ **ComfyUI 工作流导入修复 + 内置工作流原生浏览**（2026-04-13）：根因：workflow JSON 引用单文件模型名（`cogvideox5b_bf16.safetensors`、`t5xxl_fp8_e4m3fn.safetensors`），但下载脚本从 HuggingFace 获取的是分片格式。修复：(1) CogVideoX 工作流改用 `DownloadAndLoadCogVideoModel`（支持分片目录加载）；(2) 新增 T5-XXL fp8 单文件下载（4.9GB，CLIPLoader 兼容）；(3) setup.sh 自动同步工作流到 ComfyUI Browse UI。

- [ ] 到底内置工作流是怎么打开的？能不能打开comfyUI就出现在网页里，直接可以选择呢？

↑ 已解决：setup.sh 现在会自动将工作流复制到 ComfyUI 的 `user/default/workflows/` 目录，打开 ComfyUI 即可在侧栏 Browse 中直接选择。
