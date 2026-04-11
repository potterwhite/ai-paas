- **归档规则在 guide.md Section 2，不在此处** — 请读 `docs/en/1-for-ai/guide.md` ← 始终保留这行
- **归档操作**：将已完成的 items 按日期归档到 `docs/zh/2-progress/task-logs/NEED_TO_DO_ARCHIVED_YYYY-MM-DD.md`。每次 append 到最后，当日完成当日归档。
- **在此文档中的 items 都是未完成的**。
- **每次开始工作前先读取此文件**，了解当前待办状态。

> PKB目录如下：
> /Development/docker/docker-volumes/syncthing-docker/ObsidianVault/PARA-Vault/2_AREA/10-Area-Artificial_Intelligence/Project_AI_Marketing_Personal
> 1. 一切工作进度以PKB为准
> 2. 每次完成单元工作，就需要同步git/pkb
---

### 已解决（近期完成）

✅ **data 目录管理**：创建 `paas-controller.sh` 提供安全的清理、权限修复、服务控制功能。使用 `./paas-controller.sh clean-data` 清理运行时数据，`fix-permissions` 修复权限。

✅ **多模型 vLLM 支持**（2026-04-09）：Docker Compose profiles + Router 多模型切换引擎 + Webapp UI。支持 N 个 vLLM 模型（当前: Qwen 32B AWQ + Gemma 4 26B 占位）。单 GPU 同一时间只运行一个模型，Router 管理切换。

✅ **PKB 重构**（2026-04-09）：按照 `pkb-setup-guide-dup.md` 将 `Project_AI_Marketing_Personal` 重构为主题驱动的 PKB 架构。Dashboard 入口 + deploy/strategy 域分离 + 文件前缀系统 + YAML frontmatter + wiki-link 交叉引用，12/12 合规项全部通过。

✅ **WebUI 模型页面修复 + 预置模型下载**（2026-04-09）：修复 JS 语法错误（Python→JS 字符串转义）、依赖检查硬编码路径、loadPresetStatus 未调用。实现 LivePortrait 等预置工作流模型一键下载功能（从 HuggingFace 流式下载 + 实时进度）。

✅ **日志时区修复**（2026-04-09）：Docker 日志 UTC 时间戳自动转换为本地时间（Asia/Hong_Kong UTC+8），格式 `YYYY-MM-DD HH:MM:SS`。

✅ **多模型切换端到端测试 + Bug 修复**（2026-04-11）：完整测试 6 项场景全部通过（Qwen chat、工具调用、LLM↔ComfyUI 切换、无 LLM 时优雅报错）。发现并修复 Router Bug：切换到权重不存在的模型时会停掉正在运行的模型。现在 `switch_to_llm_model` 在 engine 层做 `weights_exist` 检查，两个端点（`/models/switch` 和 `/gpu/mode`）均返回 HTTP 400 并保持当前模型运行。

---

### 长期目标

- **MCP/Skills 集成**：将 MCP server 对接到 vLLM 的 tool calling 能力（`--enable-auto-tool-choice --tool-call-parser hermes`），使 OpenClaw 能使用外部工具

### 待解决问题

- **yt-dlp cookies 续期**：设计 server 端自动化从浏览器提取和更新 cookies 的机制，不依赖手动导出

### 多模型支持后续

- [ ] Gemma 4 26B A4B AWQ 量化：对 `/models/gemma-4-26B-A4B/`（BF16 ~50GB）做 AWQ 4-bit 量化，输出到 `/models/gemma-4-26B-A4B-awq/`，然后创建 vllm-gemma 容器并测试切换
- [x] 多模型切换端到端测试：Qwen ↔ Gemma 完整切换流程验证（Router API + Webapp UI）— 已测试，Gemma 需等 AWQ 权重就绪后再做实机切换

---

### Phase 4 补完

（无 — Phase 4 补完已完成并归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-07.md`）

（2026-04-09 全链路修复已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-09.md`）

（2026-04-09 MODELS_PATH 根因修复 + 硬编码路径清理已归档 ✅，详见 `task-logs/NEED_TO_DO_ARCHIVED_2026-04-09.md`）

