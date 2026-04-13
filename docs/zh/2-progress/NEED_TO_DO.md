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

（2026-04-13 ComfyUI 工作流导入修复 + 内置工作流原生浏览已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-13.md`）

### paas-controller.sh 改进

✅ **`prepare` 下载 UX 全面改进**（2026-04-13）：(1) SHA-256 校验 — 已下载文件通过 checksum 验证，不会重复下载，损坏文件自动重下；(2) 预览总览 — 启动时显示全部 6 个步骤及描述；(3) 动态进度 — `[N/6]` 步骤计数器 + CogVideoX 子步骤 `2a-2e`；(4) `realpath` 显示 — setup.sh 和 controller 都显示模型目录的真实路径；(5) 结尾摘要 — 显示下载/跳过/失败文件数。
