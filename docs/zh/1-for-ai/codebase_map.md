# ai-paas — 代码库地图（AI Agent 快速参考）

> **⚠️ AI Agent 专用 — 请先读这份文件**
> 本文档是基础设施结构的唯一权威来源。
> **不要做全目录扫描** — 读这份文件代替扫描。
>
> **维护规则：** 任何 AI Agent 修改了本文档中列出的文件，必须在同一个 commit/会话中更新本文档对应章节。
>
> 最后更新：2026-04-26（Phase 6: Vault RAG 开始实现）
>

---

## 仓库根目录结构

```
/home/james/ai-paas/                          ← Phase 4（进行中）
├── CLAUDE.md                               ← 会话入口
├── README.md                               ← 项目 README
├── docker-compose.yml                      ← 主配置 — 所有容器定义
├── .env                                    ← 本地密钥
├── .env.example                            ← .env 模板
├── .gitignore
├── paas-controller.sh                      ← 管理脚本（数据清理、服务控制）
├── models/                                 ← 模型权重文件（由 MODELS_PATH 环境变量指定宿主机路径）
│   ├── qwen2.5-32b-instruct-awq/           ←   生产模型（32B AWQ 4-bit）
│   ├── gemma-4-26B-A4B/                    ←   Gemma 4 原始权重（BF16，待 AWQ 量化）
│   └── comfyui/                            ←   ComfyUI 视频/图像模型
├── services/
│   ├── webapp/                             ←   ai_webapp 源码（FastAPI + HTML/CSS）
│   ├── router/                             ←   ai_router 源码（Phase 4）
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app/                            ←   FastAPI app
│   └── comfyui/                            ←   ComfyUI 部署脚本 + 工作流
├── data/                                   ← 运行时数据
│   ├── router_redis/                       ←   Redis data (Phase 4)
│   ├── router_db/                          ←   Router SQLite (Phase 4)
│   └── comfyui_workdir/                    ←   ComfyUI 状态
├── docs/
│   └── zh/
│       ├── 1-for-ai/guide.md               ←   工作规则
│       ├── 1-for-ai/codebase_map.md        ←   本文件
│       ├── 2-progress/progress.md          ←   Phase 索引
│       ├── 2-progress/NEED_TO_DO.md        ←   活跃待办
│       └── 2-progress/phases/phase4/plan.md←   Phase 4 详细计划
└── docs/en/                                ← 英文文档（同步自 zh）
```

---

## 逐文件参考

### `docker-compose.yml`

**多模型 vLLM 架构（Docker Compose Profiles）**

单 GPU（RTX 3090 24GB）同一时间只能运行一个 vLLM 实例。每个模型有独立的 Compose service + profile，由 Router 管理切换（停 A 启 B）。

YAML 配置使用 anchor `x-vllm-base: &vllm-base` 共享通用设置（image, volumes, deploy, shm_size, ipc 等），每个模型 service 只需覆盖 container_name, profiles, command。

**服务：`vllm-qwen`（容器：`ai_vllm_qwen`）— profile: `llm-qwen`**
- 镜像：`vllm/vllm-openai:latest`
- 端口映射：宿主机 `9997` → 容器 `8000`
- restart: `"no"` — profile-gated, Router 管理
- 模型：`/models/qwen2.5-32b-instruct-awq`（AWQ 4-bit, ~19 GB）
- 关键参数：
  - `--gpu-memory-utilization 0.95` — 32B AWQ 需 ~22 GB
  - `--max-model-len 10800` — 32B AWQ KV cache 硬上限
  - `--enable-auto-tool-choice --tool-call-parser hermes` — 工具调用
  - `--trust-remote-code` — Qwen2.5 tokenizer 需要
  - `VLLM_ENABLE_V1_MULTIPROCESSING=0` — CUDA 兼容修复
- `shm_size: 8gb`、`ipc: host`

**服务：`vllm-gemma`（容器：`ai_vllm_gemma`）— profile: `llm-gemma`**
- 同上通用配置
- 模型：`/models/gemma-4-26B-A4B-awq`（AWQ 待量化）
- `--gpu-memory-utilization 0.90`, `--max-model-len 8192`
- 状态：容器定义就绪，等待 AWQ 量化权重

**默认 profile：** `.env` 中 `COMPOSE_PROFILES=llm-qwen`，`docker compose up -d` 自动启动 Qwen。

**新模型添加步骤：**
1. 在 `docker-compose.yml` 添加新 service（使用 `<<: *vllm-base`）
2. 在 Router `config.py` 的 `VLLM_MODELS` 注册表添加条目
3. 首次创建：`docker compose --profile llm-xxx up -d vllm-xxx`
4. 之后 Router 可通过 Docker SDK start/stop 管理

**~~服务：`litellm-db` + `litellm`~~ — 已移除**
- 已被 Router（Phase 4）完全替代
- 从 docker-compose.yml 移除

**服务：`whisper`（容器：`ai_whisper`）**
- 镜像：`ghcr.io/speaches-ai/speaches:latest-cuda`
- 端口：`9998:8000`
- 模型：`Systran/faster-whisper-large-v3`（~3-4 GB 显存）
- 有 TTL 自动卸载（idle 5 min）

**服务：`comfyui`（容器：`ai_comfyui`）**
- 镜像：`yanwk/comfyui-boot:cu130-slim-v2`
- 端口：`8188:8188`
- restart: `"no"` — 必须手动启动
- ⚠️ 绝不能在任何 `ai_vllm_*` 运行时启动

**服务：`webapp`（容器：`ai_webapp`）**
- 镜像：本地构建（`services/webapp/`）
- 端口：`8888:8080`
- 路由：`/`、`/subtitle`、`/translate`、`/gpu`、`/models`

**服务：`router`（容器：`ai_router`）— Phase 4**
- 镜像：本地构建（`services/router/`）
- 端口：`4000:4000`
- 技术：FastAPI + Celery + Redis + SQLite
- 依赖：Docker socket（控制其他容器）、Redis
- 核心功能：
  - 多模型 vLLM 编排（检测活跃模型、切换模型、停启容器）
  - OpenAI 兼容 Chat API（动态路由到活跃 vLLM）
  - GPU 模式管理（LLM/ComfyUI/Idle）
  - 模型注册表（`VLLM_MODELS` in `config.py`）
- 环境：见 `docker-compose.yml` router service

**服务：`router-redis`（容器：`ai_router_redis`）— Phase 4**
- 镜像：`redis:7-alpine`
- 端口：不暴露到宿主机
- 用途：Celery broker + result backend

---

### API 接口

### API 网关（ai_router :4000）

**生产接口：**
```
POST http://192.168.0.19:4000/v1/chat/completions  ← Router 动态路由到活跃 vLLM
Body: {"model": "qwen", "messages": [...]}
```

**Router 统一接口（Phase 4）：**
```
POST /v1/chat/completions             → OpenAI 兼容（动态路由到活跃 vLLM）
POST /v1/audio/transcriptions         → Whisper 直连
GET  /v1/gpu                          → GPU 状态 + 活跃模型 + 容器状态
POST /v1/gpu/mode                     → GPU 模式切换（llm/comfyui + 指定模型）
POST /v1/gpu/containers               → 容器管理（start/stop/restart）
GET  /v1/models                       → 本地模型列表
GET  /v1/models/available             → 已注册可切换模型列表
POST /v1/models/switch                → 切换活跃 LLM 模型
POST /v1/models/download              → 从 HuggingFace 下载模型
GET  /v1/health                       → Router 健康检查
```

### Web UI（ai_webapp :8888）
```
http://192.168.0.19:8888/           → 首页 + 显存面板
http://192.168.0.19:8888/gpu        → GPU 面板 + 启停容器
http://192.168.0.19:8888/models     → 模型管理
http://192.168.0.19:8888/status     → JSON API
```

### Whisper STT（:9998）
```
POST http://192.168.0.19:9998/v1/audio/transcriptions  → 转录音频
```

### ComfyUI（:8188）
```
POST http://192.168.0.19:8188/prompt   → 提交工作流
GET  http://192.168.0.19:8188/queue    → 查看队列
```
> ⚠️ 必须手动启动。绝不能在任何 ai_vllm_* 运行时启动。

### 调试专用（直连 vLLM :9997）
```
POST http://192.168.0.19:9997/v1/chat/completions
Body: {"model": "/models/qwen2.5-32b-instruct-awq", "messages": [...]}
```
> 注意：端口 9997 映射到当前活跃的 vLLM 容器（ai_vllm_qwen 或 ai_vllm_gemma）。

### OpenClaw 专用配置
```
API Base URL:  http://192.168.0.19:4000/v1
API Key:       sk-CsNbakApBdKkWut0qf2jVA
Model Name:    qwen
```

---

## 活跃容器

| 容器 | 镜像 | 状态 | 用途 |
|---|---|---|---|
| `ai_vllm_qwen` | `vllm/vllm-openai:latest` | ✅ 运行中（默认） | LLM 推理 — Qwen 2.5 32B AWQ |
| `ai_vllm_gemma` | `vllm/vllm-openai:latest` | ⏸ 待创建（AWQ 权重未就绪） | LLM 推理 — Gemma 4 26B A4B |
| `ai_whisper` | `ghcr.io/speaches-ai/speaches:latest-cuda` | ✅ 运行中 | STT |
| `ai_webapp` | 本地构建 | ✅ 运行中 | Web UI |
| `ai_comfyui` | `yanwk/comfyui-boot:cu130-slim-v2` | ⏸ 停止（仅手动） | 视频/图像生成 |
| `ai_router` | 本地构建 | ✅ 运行中 | GPU Router / 多模型编排 |
| `ai_router_redis` | `redis:7-alpine` | ✅ 运行中 | Celery broker + cache |
| `ai_router_worker` | 本地构建 | ✅ 运行中 | Celery 异步任务 |

---

## GPU / 显存分配

| 场景 | 活跃容器 | 显存占用 |
|---|---|---|
| LLM 模式 — Qwen 32B（默认） | ai_vllm_qwen | ~22 GB（gpu-util 0.95） |
| LLM 模式 — Gemma 4 26B（待量化） | ai_vllm_gemma | ~13 GB（估算，AWQ 4-bit） |
| 视频生成 | ai_comfyui 独占 | 最高 24 GB |

⚠️ **同一时间只能运行一个 vLLM 实例。vLLM 和 ComfyUI 不能同时运行。** Router 自动管理互斥（切换时先停再启）。

---

## 磁盘上的模型

| 模型 | 路径 | 大小 | 状态 |
|---|---|---|---|
| Qwen 2.5 32B Instruct AWQ | `models/qwen2.5-32b-instruct-awq/` | ~19 GB | ✅ 生产中 |
| Gemma 4 26B A4B（BF16 原始） | `models/gemma-4-26B-A4B/` | ~50 GB | ⏸ 需 AWQ 量化 |
| ComfyUI 模型 | `models/comfyui/` | ~31 GB | ⏸ ComfyUI 专用 |

**模型存储路径：** 由 `.env` 中 `MODELS_PATH` 控制（默认 `./models`，当前指向 `/Development/docker/docker-volumes/ai_paas`）。
