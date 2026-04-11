# Phase 1 — 计算中枢

> 状态：✅ 已完成 | 完成时间：2026-03-22
> **索引：** [← progress.md（英文）](../../../en/2-progress/progress.md) | [英文版 →](../../../en/2-progress/phases/phase1/plan.md)

---

## 目标

搭建稳定的 GPU 加速 LLM 推理栈，能够支持 OpenClaw Agent 工具调用，使用 14B 参数模型。
这是所有后续 Phase 依赖的基础设施。

---

## 本阶段架构决策

| 决策 | 选择 | 原因 |
|---|---|---|
| 推理引擎 | vLLM（官方 Docker 镜像） | Xinference 有无法修复的 CUDA spawn 嵌套 bug |
| API 网关 | LiteLLM | 模型别名 + 虚拟 Key 管理 + Web UI + 单一控制点 |
| LiteLLM 数据库 | PostgreSQL | Prisma ORM 不支持 SQLite，PostgreSQL 是强制要求 |
| 显存分配 | `gpu_memory_utilization=0.7` | 从 0.5 提升到 0.7 满足 16k 上下文；为 Phase 2 Whisper 预留 ~7 GB |
| 工具调用解析器 | `--tool-call-parser hermes` | Qwen 2.5 使用 Hermes 格式；不加此参数 OpenClaw agent loop 会永远失败 |
| 模型 | Qwen 2.5 14B Instruct AWQ（Int4） | 24 GB 可装下，推理能力强，支持工具调用，与 OpenClaw 兼容 |

详细原因参见：[`architecture_vision.md`](../../../en/3-highlights/architecture_vision.md)

---

## 步骤记录

| 步骤 | 描述 | 状态 | Commit |
|---|---|---|---|
| **1.1** | 初始 Docker 栈：vLLM + LiteLLM，Qwen 1.5B AWQ 测试模型 | ✅ `2203b16` | `2203b16` |
| **1.2** | 添加交接文档，记录完整系统状态 | ✅ `ef4935a` | `ef4935a` |
| **1.3** | 切换到 14B 生产模型；为 LiteLLM UI 添加 PostgreSQL；VRAM 提升到 0.7；发放 OpenClaw 虚拟 Key | ✅ `3f39fbf` | `3f39fbf` |
| **1.4** | 启用工具调用支持（`--enable-auto-tool-choice --tool-call-parser hermes`） | ✅ `bb99ea5` | `bb99ea5` |
| **1.5** | 文档重建：AI-First 双语文档结构 + CLAUDE.md + phase plan 文件 | ✅ `b8be598` | `b8be598` |
| **1.6** | 目录整理：删废弃文件，data/ 整合，.env 机制，双语 README | ✅ `89360cc` `523fda3` | `89360cc` |

---

## 已验证可用 ✅

- vLLM v0.18.0 运行 Qwen 2.5 14B Instruct AWQ（Int4）— 9.4 GB 权重
- 显存锁定在 70%（约 17 GB），通过 `gpu_memory_utilization=0.7`
- 16 384 token 上下文窗口（满足 OpenClaw 最低要求）
- LiteLLM 网关将别名 `"qwen"` 路由到 vLLM `http://ai_vllm:8000/v1`
- LiteLLM Web UI 在 `:4000/ui`，PostgreSQL 持久化存储
- OpenClaw（192.168.0.11）已接入，Agent 工具调用正常工作
- Portainer 在 `:9000`，Harbor 在 `:8080`

---

## 关键配置值（Phase 1 最终状态）

**vLLM 启动参数（`docker-compose.yml`）：**
```
--model /models/qwen2.5-14b-instruct-awq
--gpu-memory-utilization 0.7
--max-model-len 16384
--enable-auto-tool-choice
--tool-call-parser hermes
--trust-remote-code
```

**LiteLLM 路由别名（`litellm_config.yaml`）：**
```yaml
model_name: qwen
litellm_params:
  model: openai//models/qwen2.5-14b-instruct-awq
  api_base: http://ai_vllm:8000/v1
```

**OpenClaw 虚拟 Key：**
- Key：`sk-CsNbakApBdKkWut0qf2jVA`（别名：`openclaw-agent`）
- 授权模型：`["qwen"]`
- 注意：model string 使用 `"qwen"`，不是 `"litellm/qwen"`（后者在 LiteLLM 1.82.1+ 返回 400）

---

## 已排查问题记录

| 问题 | 解决方案 |
|---|---|
| LiteLLM 不支持 SQLite | 步骤 1.3 修复 — 切换到 PostgreSQL |
| 1.5B 测试模型不够用于生产 | 步骤 1.3 修复 — 替换为 14B AWQ |
| 没有 hermes 解析器工具调用失败 | 步骤 1.4 修复 |
| Xinference CUDA spawn bug | 彻底放弃 Xinference（详见 `archived/`） |
| `VLLM_USE_V1=0` 环境变量不存在 | 移除，替换为 `VLLM_ENABLE_V1_MULTIPROCESSING=0` |
| `VLLM_ENABLE_V1_MULTIPROCESSING=false` 类型错误 | 修复：必须是整数 `0`，不能是字符串 `false` |
| 根目录散乱（废弃文件、硬编码密钥） | 步骤 1.6 修复：`89360cc` |
