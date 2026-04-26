# ai-paas — 进度索引

> 最后更新：2026-04-02
> **英文版：** [English →](../../en/2-progress/progress.md)

本文件是导航索引。每个 Phase 有独立的计划文件，包含完整步骤记录、架构决策和配置值。

---

## 总体状态

| Phase | 描述 | 状态 | 计划文件 |
|---|---|---|---|
| **Phase 1** | 计算中枢 — vLLM + LiteLLM + 基础设施 | ✅ 完成 | [phases/phase1/plan.md](phases/phase1/plan.md) · [English](../../en/2-progress/phases/phase1/plan.md) |
| **Phase 2** | 音视频翻译 — Whisper + Web UI（字幕/翻译/GPU面板）| ✅ 完成 | [phases/phase2/plan.md](phases/phase2/plan.md) · [English](../../en/2-progress/phases/phase2/plan.md) |
| **Phase 3** | 视觉生成 & 数字人 — ComfyUI + 显存切换 | ✅ 完成 | [phases/phase3/plan.md](phases/phase3/plan.md) · [English](../../en/2-progress/phases/phase3/plan.md) |
| **Phase 4** | GPU Router / Orchestrator — 统一入口、GPU 独占调度、替代 LiteLLM、多模型切换 | ✅ 完成 | [phases/phase4/plan.md](phases/phase4/plan.md) · [English](../../en/2-progress/phases/phase4/plan.md) |
| **Phase 5** | SynapseERP 集成 — Agent-First ERP，ai-paas 作为基础设施层 | ⏳ 规划中 | [phases/phase5/plan.md](phases/phase5/plan.md) · [English](../../en/2-progress/phases/phase5/plan.md) |
| **Phase 6** | Vault RAG — Obsidian 知识库 AI 查询系统 | 🔄 实现中 | [vault_rag_design.md](../3-highlights/vault_rag_design.md) |

**当前状态：** Phase 4 完成（4.1-4.6 + 多模型支持）。Phase 5 为远期规划（SynapseERP 业务层调用 ai-paas 基础设施）。
2026-04-05：Phase 4 架构设计完成，Phase 3 时分调度方案归档（[详情](../../en/3-highlights/archived/phase3_manual_gpu_switch_archived.md)）。
2026-04-09：多模型 vLLM 支持完成 — Docker Compose profiles + Router 多模型切换 + Webapp UI。

---

## Phase 1 提交记录（已完成）

| 步骤 | 描述 | Commit |
|---|---|---|
| 1.1 | 初始栈：vLLM + LiteLLM + 1.5B 测试模型 | `2203b16` |
| 1.2 | 交接文档 | `ef4935a` |
| 1.3 | 切换 14B 模型 + PostgreSQL + VRAM 0.7 + OpenClaw Key | `3f39fbf` |
| 1.4 | 工具调用支持（`--enable-auto-tool-choice --tool-call-parser hermes`） | `bb99ea5` |
| 1.5 | 文档重建：AI-First 双语结构 + CLAUDE.md | `b8be598` |
| 1.6 | 目录清理：删废弃文件、data/ 整合、.env、双语 README | `89360cc` `523fda3` |

---

## Phase 2 提交记录（已完成）

| 步骤 | 描述 | Commit |
|---|---|---|
| 2.1 | 编写 Phase 2 计划（`phases/phase2/plan.md`） | `b8be598` |
| 2.2 | 添加 `ai_whisper`（speaches:latest-cuda）；CUDA 测试；显存共存验证（峰值 ~22GB，空闲 ~18GB，TTL 驱逐确认） | `ebc4daf` |
| 2.3–2.7 | Whisper LiteLLM 路由；webapp Dockerfile + FastAPI；字幕/翻译/GPU 页面；响应式 CSS | `ebc4daf` |
| 2.8 | 端到端测试 + 修复 Whisper URL bug（原来经 LiteLLM 路由，改为直连 ai_whisper） | `34155de` |
| 2.9 | 文档同步：codebase_map + progress.md 标记 Phase 2 ✅ 完成 | `34155de` |

---

## Phase 3 提交记录（进行中）

| 步骤 | 描述 | Commit |
|---|---|---|
| 3.2 | 添加 ai_comfyui 到 docker-compose；验证 GPU 直通 | `b649156` |
| 3.3 | CogVideoX-5B 工作流；修正模型格式（fcd8039）；install-nodes + download-models + gpu-switch.sh | `fcd8039` |
| 磁盘清理 | 删除 3 个冗余模型目录，释放 20GB | `8b5cf46` |
| 32B 升级 | vLLM 升级 Qwen2.5-32B-AWQ；gpu_memory_utilization 0.7→0.95；max_model_len=10800 | `ab79c12` `202e06f` |
| /models UI | WebUI /models 页面上线 — HuggingFace 模型管理器 | `122e2df` |

---

**Phase 4 提交记录（实现中）**

| 步骤 | 描述 | Commit |
|---|---|---|
| 4.1 | Router 骨架：FastAPI + Celery + Redis + SQLite | `d0f8862` |
| 4.2 | GPU 监控：pynvml + Docker SDK，`/api/v1/gpu` | `98bbf70` |
| 4.3 | LLM 代理：`/api/v1/chat/completions` + 鉴权中间件 | `453b28d` |
| 4.4 | GPU 调度：Celery switch + queue logic | `8265dd3` |
| 4.5-4.6 | 模型管理 + 多模型 vLLM：Compose profiles, Router 切换引擎, Webapp UI | `542e66d` |

---

## 附录 — 已记录的失败方案

| 方案 | 失败原因 | 参考 |
|---|---|---|
| Xinference（xprobe/xinference:latest） | CUDA spawn bug：3 层进程嵌套破坏 `torch._C._cuda_init()` | [`archived/xinference-debug-full-log.md`](../../en/3-highlights/archived/xinference-debug-full-log.md) |
| LiteLLM + SQLite | Prisma ORM 拒绝非 PostgreSQL URL | Phase 1.3 修复 |
| `VLLM_USE_V1=0` 环境变量 | vLLM 0.13.0+ 中不存在 | [`archived/troubleshooting-log.md`](../../en/3-highlights/archived/troubleshooting-log.md) |
| `VLLM_ENABLE_V1_MULTIPROCESSING=false` | 类型错误，必须是整数 `0` | 同上 |
| `litellm/qwen` 模型字符串 | LiteLLM 1.82.1+ 返回 400，只有 `qwen` 有效 | Phase 1.5 修复，2026-03-28 验证 |
| Qwen2.5-72B AWQ + cpu-offload | RTX 3090 PCIe 带宽限制导致仅 0.5-2 tok/s | 2026-04-02 调研，已否决 |
