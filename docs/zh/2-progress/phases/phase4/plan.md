# Phase 4 — GPU Router / Orchestrator

> **Status:** Design complete, implementation ready | **Created:** 2026-04-05
> **English version：** [English →](../../../en/2-progress/phases/phase4/plan.md)

---

## 目标

构建一个独立的 `ai_router` 服务（FastAPI + Celery + Redis），替代 LiteLLM + PostgreSQL，实现：
1. **统一 API 入口** — 所有客户端只连 `ai_router:4001`（最终切到 4000）
2. **GPU 独占调度** — vLLM 与 ComfyUI 自动切换，排队等待
3. **可扩展 Provider 架构** — 新服务只需加一个 `BackendProvider` 文件

---

## 架构

```
客户端 ──▶ ai_router:4001 (FastAPI)
              │
              ├─ LLM 请求 → vLLM:8000 (直连 / 排队后转发)
              ├─ Audio 请求 → Whisper:9998 (TTL 自动卸载)
              └─ Visual 请求 → ComfyUI:8188 (GPU 切换后执行)
              │
              ├─ GPU 调度 / 容器启停 / 排队 ◀── Celery Workers
              └─ Redis (消息队列) + SQLite (任务持久化)
```

**为什么去掉 LiteLLM：** LiteLLM 在 ai-paas 中只做 3 件事——模型别名映射、key 管理、协议转发。vLLM 和 Whisper 本身都是 OpenAI 兼容 API，不需要协议转换。Router 可以覆盖这 3 件事 + 多了 GPU 调度能力。

**为什么独立项目（不是 SynapseERP 的模块）：** Django 同步模型不适合作为重载 API 网关 + GPU 调度器。两个领域职责不相关。

**为什么 Celery 而不是 Ray/SkyPilot：** 单卡场景下 Ray 10 倍复杂度，SkyPilot 面向多云。Celery + Redis 最轻量且已有可视化工具（Flower）。

---

## 目录结构

```
services/router/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py               # FastAPI 入口（≤50 行）
│   ├── config.py             # 配置管理
│   ├── api/routes/           # HTTP 端点（gateway / tasks / queue / gpu）
│   ├── api/deps.py           # 鉴权中间件
│   ├── core/                 # 核心逻辑（gpu_monitor / container_mgr / health_checker / router_engine）
│   ├── workers/              # Celery 异步任务（celery_app / tasks）
│   ├── models/               # SQLAlchemy 数据模型（task / response）
│   └── providers/            # ★ 扩展点：每个后端服务一个 Provider 文件
│       ├── base.py           #   BackendProvider 抽象基类
│       ├── vllm_provider.py
│       ├── whisper_provider.py
│       └── comfyui_provider.py
```

---

## API 端点

| 端点 | 说明 |
|---|---|
| `POST /api/v1/chat/completions` | OpenAI 兼容，OpenClaw 无需改代码 |
| `POST /api/v1/audio/transcriptions` | Whisper 直连 |
| `GET/POST /api/v1/tasks[/{id}]` | 查询任务状态 |
| `GET /api/v1/queue` | 当前排队任务 |
| `GET /api/v1/gpu` | GPU 状态 |
| `GET/POST /api/v1/models[/switch|/download]` | 模型管理 |
| `GET/POST/DELETE /api/v1/keys` | API Key 管理 |
| `GET /api/v1/health` | Router 自身健康检查 |

---

## 迭代路径

| 步骤 | 描述 | 状态 |
|---|---|---|
| **4.1** | 骨架：FastAPI + Celery + Redis | ✅ 完成 | `d0f8862` |
| **4.2** | GPU 监控 + 容器状态（pynvml + Docker SDK） | ✅ 完成 | `98bbf70` |
| **4.3** | LLM 代理：/api/v1/chat/completions → vLLM | ✅ 完成 | `453b28d` |
| **4.4** | GPU 调度：Celery 切换容器 + 排队逻辑 | ✅ 完成 | `8265dd3` |
| **4.5** | 迁移：端口 → 4000，停 LiteLLM + PostgreSQL | ✅ 完成 | |
| **4.6** | Whisper + ComfyUI Provider + 模型管理 | ✅ 完成 | |

---

## 显存预算

| 场景 | 活跃容器 | 显存 |
|---|---|---|
| 文字推理（默认） | vLLM 32B AWQ | ~22 GB |
| 文字 + Whisper（14B 降级） | vLLM 14B + Whisper | ~21 GB |
| 视觉生成 | ComfyUI 独占 | 最高 24 GB |
| ⚠️ vLLM 和 ComfyUI **永远不同时运行** | | |
