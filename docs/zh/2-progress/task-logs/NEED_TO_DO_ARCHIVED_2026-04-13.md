# 归档 — 2026-04-13

---

✅ **Google Release-Please 自动化**（2026-04-12）：配置 `release-please-config.json` + `.release-please-manifest.json`，添加 `.github/workflows/release-please.yml` GitHub Actions。push 到 main 后自动生成 CHANGELOG.md 和 GitHub Release（v2.0.0、v2.1.0 已自动发布）。

✅ **MIT License Header CI 检查**（2026-04-12）：添加 `LICENSE` 文件和 `.github/workflows/license-check.yml`，使用 `google/addlicense` 工具自动检查所有 `.py`/`.sh`/`.bash` 源文件是否包含 MIT license header。所有现有源文件已补齐 header。

✅ **data 目录管理**：创建 `paas-controller.sh` 提供安全的清理、权限修复、服务控制功能。使用 `./paas-controller.sh clean-data` 清理运行时数据，`fix-permissions` 修复权限。

✅ **多模型 vLLM 支持**（2026-04-09）：Docker Compose profiles + Router 多模型切换引擎 + Webapp UI。支持 N 个 vLLM 模型（当前: Qwen 32B AWQ + Gemma 4 26B 占位）。单 GPU 同一时间只运行一个模型，Router 管理切换。

✅ **PKB 重构**（2026-04-09）：按照 `pkb-setup-guide-dup.md` 将 `Project_AI_Marketing_Personal` 重构为主题驱动的 PKB 架构。Dashboard 入口 + deploy/strategy 域分离 + 文件前缀系统 + YAML frontmatter + wiki-link 交叉引用，12/12 合规项全部通过。

✅ **WebUI 模型页面修复 + 预置模型下载**（2026-04-09）：修复 JS 语法错误（Python→JS 字符串转义）、依赖检查硬编码路径、loadPresetStatus 未调用。实现 LivePortrait 等预置工作流模型一键下载功能（从 HuggingFace 流式下载 + 实时进度）。

✅ **日志时区修复**（2026-04-09）：Docker 日志 UTC 时间戳自动转换为本地时间（Asia/Hong_Kong UTC+8），格式 `YYYY-MM-DD HH:MM:SS`。

✅ **多模型切换端到端测试 + Bug 修复**（2026-04-11）：完整测试 6 项场景全部通过（Qwen chat、工具调用、LLM↔ComfyUI 切换、无 LLM 时优雅报错）。发现并修复 Router Bug：切换到权重不存在的模型时会停掉正在运行的模型。现在 `switch_to_llm_model` 在 engine 层做 `weights_exist` 检查，两个端点（`/models/switch` 和 `/gpu/mode`）均返回 HTTP 400 并保持当前模型运行。

✅ **ComfyUI 工作流浏览器**（2026-04-12）：webapp `/comfyui` 页面新增动态工作流浏览器，展示全部 6 条内置工作流（按图像/视频/数字人分类），每条工作流显示名称、描述、模型就绪状态和下载 JSON 按钮。新增 `/api/comfyui/workflows` 列表接口和 `/api/comfyui/workflows/{filename}` 下载接口。

✅ **多模型切换端到端测试**（2026-04-11）：Qwen ↔ Gemma 完整切换流程验证（Router API + Webapp UI）— 已测试，Gemma 需等 AWQ 权重就绪后再做实机切换。

✅ **ComfyUI 工作流导入修复 + 内置工作流原生浏览**（2026-04-13）：根因：workflow JSON 引用单文件模型名（`cogvideox5b_bf16.safetensors`、`t5xxl_fp8_e4m3fn.safetensors`），但下载脚本从 HuggingFace 获取的是分片格式。修复：(1) CogVideoX 工作流改用 `DownloadAndLoadCogVideoModel`（支持分片目录加载）；(2) 新增 T5-XXL fp8 单文件下载（4.9GB，CLIPLoader 兼容）；(3) setup.sh 自动同步工作流到 ComfyUI Browse UI。打开 ComfyUI 即可在侧栏 Browse 中直接选择内置工作流。

✅ **`prepare` 下载 UX 全面改进**（2026-04-13）：(1) SHA-256 校验 — 已下载文件通过 checksum 验证，不会重复下载，损坏文件自动重下；(2) 预览总览 — 启动时显示全部 6 个步骤及描述；(3) 动态进度 — `[N/6]` 步骤计数器 + CogVideoX 子步骤 `2a-2e`；(4) `realpath` 显示 — setup.sh 和 controller 都显示模型目录的真实路径；(5) 结尾摘要 — 显示下载/跳过/失败文件数。
