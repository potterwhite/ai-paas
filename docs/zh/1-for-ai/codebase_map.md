# ai-paas — 代码库地图（AI Agent 快速参考）

> **⚠️ AI Agent 专用 — 请先读这份文件**
> 本文档是基础设施结构的唯一权威来源。
> **不要做全目录扫描** — 读这份文件代替扫描。
>
> **维护规则：** 任何 AI Agent 修改了本文档中列出的文件，必须在同一个 commit/会话中更新本文档对应章节。
>
> 最后更新：2026-08-18（idphoto 纳入 Router GPU 调度；新增 `config/gpu-registry.json` 作为 GPU 容器唯一配置源；`0-entrypoint.sh` 让依赖只装一次；`stop_services` 改用 `docker compose stop` 保住容器层）
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
├── models-link → ${MODELS_PATH}            ← 符号链接，`prepare` 建 / `cleanall` 删（git-ignored）
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
│   ├── idphoto/                            ←   HivisionIDPhotos 手动安装沙箱（整目录挂 /opt/idphoto:ro）
│   │   ├── Dockerfile                      ←     空壳镜像（仅 apt 系统库，无 pip 包）
│   │   ├── requirements.txt                ←     我们修正过的依赖（**不是**上游那份）
│   │   ├── 1-download-weights.sh           ←     宿主机跑：aria2c 下 2 个 onnx + 校验字节数
│   │   ├── 2-install.sh                    ←     容器内跑：装依赖 + 断言 get_device()==GPU
│   │   ├── 3-run.sh                        ←     容器内跑：起 WebUI（app.py，内网 :7860）
│   │   └── README.md                       ←     5 步安装 + 两个静默陷阱
│   └── comfyui/                            ←   ComfyUI 部署脚本 + 工作流
├── data/                                   ← 运行时数据
│   ├── router_redis/                       ←   Redis data (Phase 4)
│   ├── router_db/                          ←   Router SQLite (Phase 4)
│   ├── idphoto/                            ←   已迁出 → `${MODELS_PATH}/idphoto`（独立 1 TB 盘）
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

### `config/gpu-registry.json` — GPU 容器唯一配置源

所有「碰 GPU 的容器」只在这里登记一次。改容器、加容器、删容器,先看这个文件。

消费方（4 个,全部从这里派生,不再各自硬编码）:
- `services/router/app/config.py` → `GPU_CONTAINERS` / `VLLM_MODELS` / `GPU_SERVICES` / `DEFAULT_LLM_MODEL`
- `services/router/app/api/routes/gpu.py` → 白名单 `MANAGED_CONTAINERS`、可选模式 `GPU_MODES`
- `services/webapp/main.py` → `/gpu` 面板的互斥提示、启动耗时估算、显示名、日志容器列表
- `scripts/core.sh` → `gpu_profile_flags()` / `gpu_exclusive_services()`（用 `jq` 读）

关键字段:
- `exclusive: true` — 独占整张卡,Router 启动它前会停掉所有其他 exclusive 容器
- `compose_service` — docker-compose.yml 里的 service key,**和注册表 key 不同**
  （如 key `qwen-32b` ↔ service `vllm-qwen`）
- `profile` — compose profile 名;`null` 表示不门控（如 whisper 随平台常驻）

**真正的 GPU 互斥在 `services/router/app/core/router_engine.py`,不在 profile。**
profile 只是启动过滤器,作用是让 `docker compose up -d` 只*创建*容器不启动,
把调度权交给 Router。

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
2. 在 `config/gpu-registry.json` 的 `containers` 添加条目（`type: "vllm"`, `exclusive: true`）
3. 首次创建：`docker compose --profile llm-xxx up -d --no-start vllm-xxx`
4. 之后 Router 可通过 Docker SDK start/stop 管理

⚠️ 这两个文件必须同改：compose 读不了 JSON（`profiles:` 必须是字面 YAML），
所以容器名 / profile / 模型路径在两边各存一份。**不要**再去改 `config.py`。

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

**服务：`rag`（容器：`ai_rag`）— Phase 6**
- 镜像：本地构建（`services/rag/`）
- 端口：`8081:8081`
- 技术：FastAPI + ChromaDB + BGE embedding
- 核心功能：
  - `/v1/vault/query` — 查询 Vault + LLM 生成回答
  - `/v1/vault/write` — 写回 Vault（新建/追加）
  - `/v1/vault/index/rebuild` — 重建索引
- 依赖：Router（调用 LLM）、Vault volume、ChromaDB volume
- 环境：见 `docker-compose.yml` rag service

**服务：`idphoto`（容器：`ai_idphoto`）— profile: `idphoto`**
- 镜像：本地构建（`services/idphoto/`）— **故意做成空壳**
- 端口：**都不发布**。Gradio 的 `7860` 和 `deploy_api.py` 的 `8080` 仅内网可达；
  浏览器入口是 ai_webapp 的 **`:8888/idphoto`**（反代到 `/idphoto/ui`）
- restart: `"no"`，profile 门控 — 默认不启动，不写进 `COMPOSE_PROFILES`
- **GPU 模式：已注册进 `config/gpu-registry.json`（`exclusive: true`）。**
  Router 把它当一等 GPU 服务调度：`POST /v1/gpu/mode {"mode":"idphoto"}` 会先停掉
  vLLM/ComfyUI 再启动它；切回 `{"mode":"llm"}` 则停掉它。也可用 webapp `/gpu` 面板点
- **依赖装一次即可。** `0-entrypoint.sh` 在容器启动时探测 pip 包：
  装了 → 直接起 `3-run.sh`（WebUI）；没装 → 打印安装命令并 idle 挂住（不崩溃重启）
- 用途：HivisionIDPhotos AI 证件照（抠图 → 换底色 → 标准尺寸裁切）
- **安装方式：手动。** 镜像里只有 apt 系统库（opencv 的 `libGL` 依赖），
  零 pip 包、零应用代码。用户 `docker exec` 进去自己装。
  完整步骤见 `services/idphoto/README.md`
- 底座：`nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04`（Ubuntu 22.04 → python 3.10，
  满足项目 `numpy<=1.26.4` 约束；带 **cuDNN 9.5.1**）
- 持久化（bind mount，删容器不丢）：
  - `${MODELS_PATH}/idphoto/src` → `/workspace` — git clone + 模型权重
  - `${MODELS_PATH}/idphoto/pip-cache` → `/root/.cache/pip` — 重装走缓存
  - `./services/idphoto` → `/opt/idphoto:ro` — 我们的脚本 + `requirements.txt`
  - ⚠️ 放在 `MODELS_PATH`（`/Development`，独立 1 TB 盘）而非仓库内 —
    权重 + pip 缓存近 1 GB，不占 196 GB 系统盘。
  - ⚠️ **挂目录而非单文件** — 单文件 bind mount 绑源文件 inode，宿主机改文件换了
    inode 后容器仍读到旧内容。挂目录按路径解析，改完立即生效。
- 安装/重置（GPU only，无设备切换）：
  ```
  bash services/idphoto/1-download-weights.sh                    # 宿主机
  docker compose --profile idphoto up -d --build idphoto
  docker exec -it ai_idphoto bash /opt/idphoto/2-install.sh      # 容器内
  docker exec -it ai_idphoto bash /opt/idphoto/3-run.sh          # 容器内 → 经 8888 反代访问
  ```
  重来：`docker rm -f ai_idphoto` 后回到第 2 条。
- ⚠️ **上游 clone 永不修改** — `${MODELS_PATH}/idphoto/src` 保持 upstream 干净状态。
  所有修正在 `services/idphoto/requirements.txt`，不动上游那份。
- ⚠️ **两个静默陷阱**（都不报错，只是结果错，故 `2-install.sh` 结尾必须断言）：
  1. 上游 `requirements.txt` 写 CPU 专用的 `onnxruntime`，装它 `get_device()` 永远返回
     `"CPU"`（`hivision/creator/human_matting.py:40`），**静默走 CPU、慢十倍**。
  2. `onnxruntime-gpu` ≤1.18 链 `libcudnn.so.8`，≥1.19 链 `libcudnn.so.9`。底座镜像只有
     `.so.9`，装 1.18 加载不到 CUDA provider，**又是静默回退 CPU**。上游 README 写 1.18.0
     是因为它假设 cuDNN 8。故须 `onnxruntime-gpu>=1.19,<1.20`。
  - 上游提到的 `pip install torch` **不需要** — 那只是给 cuDNN 配不好的人借 torch 自带的
    cuDNN，我们镜像里 cuDNN 是好的，省 ~2.5 GB。
  - 上游 `requirements.txt` 还漏了 `Pillow`（`hivision/utils.py:3` 用到）。
  - `gradio` 即使只跑 API 也必须装 —— `hivision/plugin/beauty/__init__.py` 无条件
    import `beauty_tools` → `grind_skin`，后者在模块级构建 `gr.Blocks`。
- ⚠️ **必须先停所有 `ai_vllm_*`** — birefnet-v1-lite 需 ~16 GB 显存，
  vLLM 占 24 GB 中的 ~22 GB，单卡装不下。
- WebUI 与 API 是两个入口：`app.py`（Gradio，容器内 :7860，有页面）vs `deploy_api.py`
  （FastAPI，:8080，7 个 POST 接口、**无页面**，留给 ai_webapp 集成）。
- ⚠️ **WebUI 走 ai_webapp 反代，不发布 7860**。三处咬合，改一个要一起改：
  `GRADIO_ROOT_PATH=/idphoto/ui`（compose）≡ `IDPHOTO_PREFIX`（`services/webapp/main.py`），
  且代理必须转发 `x-forwarded-host`（否则 Gradio 把内网地址写进前端 config，页面空白），
  SSE 读超时必须为 `None`（否则长推理被掐断）。细节见 `services/idphoto/README.md`。
- 抠图模型画质排序：`birefnet-v1-lite`（214MB，最好，唯一支持 GPU）> `rmbg-1.4`（176MB）> `modnet`（24.7MB）
  当前只下载了 `birefnet-v1-lite` + `retinaface-resnet50`。

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

### Vault RAG（ai_rag :8081）
```
POST http://192.168.0.19:8081/v1/vault/query     → 查询 Vault + LLM 回答
POST http://192.168.0.19:8081/v1/vault/write     → 写回 Vault
POST http://192.168.0.19:8081/v1/vault/index/rebuild → 重建索引
GET  http://192.168.0.19:8081/v1/health          → 健康检查
```

### AI 证件照（ai_idphoto）

**WebUI（当前入口）**
```
http://192.168.0.19:8888/idphoto        → 落地页（状态 + 一键切 GPU + iframe 内嵌 Gradio）
http://192.168.0.19:8888/idphoto/ui/    → 反代到 ai_idphoto:7860（上游原版 Gradio）
```
7860 不对外发布。

**API（`deploy_api.py`，容器内 :8080，不对外发布，留给 ai_webapp 集成）**
```
POST http://ai_idphoto:8080/idphoto                 → 证件照（抠图+裁切+底色）
POST http://ai_idphoto:8080/human_matting           → 仅抠图
POST http://ai_idphoto:8080/add_background          → 仅换底色
POST http://ai_idphoto:8080/generate_layout_photos  → 六寸排版照
POST http://ai_idphoto:8080/watermark               → 加水印
POST http://ai_idphoto:8080/set_kb                  → 指定文件大小(KB)
POST http://ai_idphoto:8080/idphoto_crop            → 仅裁切（不抠图）
```
> ⚠️ `deploy_api.py` **没有任何页面**，浏览器打开是空的。WebUI 是 `app.py`。
> ⚠️ API 仅容器内部网络可达，宿主机无端口映射。ai_webapp 通过容器名访问。
> profile 门控，默认不启动：`docker compose --profile idphoto up -d idphoto`
> 应用需手动安装，见 `services/idphoto/README.md`。
> ⚠️ `/idphoto` 默认 `human_matting_model=modnet_photographic_portrait_matting`，
> 但该权重**未下载**。画质优先且必须显式传：
> `human_matting_model=birefnet-v1-lite` + `face_detect_model=retinaface-resnet50`

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
| `ai_rag` | 本地构建 | ⏸ 停止（Phase 6 新建） | Vault RAG / 知识库查询 |
| `ai_idphoto` | 本地构建（空壳） | ⏸ 停止（profile 门控，手动装） | AI 证件照 — HivisionIDPhotos |

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

设置了 `MODELS_PATH` 时，`./paas-controller.sh prepare` 会在仓库根目录建立 `models-link` 符号链接
指向该路径（`scripts/core.sh` → `ensure_models_link()`），`cleanall` 用 `remove_models_link()` 删除它。
链接已加入 `.gitignore`，仅为本机浏览方便 — 容器挂载仍直接使用 `MODELS_PATH` 绝对路径。

## 运行时数据目录

| 目录 | 位置 | 用途 |
|------|------|------|
| `router_db` | `./data/router_db` | Router SQLite 数据库 |
| `router_redis` | `./data/router_redis` | Redis 持久化数据 |
| `rag_chroma` | `./data/rag_chroma` | ChromaDB 向量索引 |
| `idphoto` | `${MODELS_PATH}/idphoto` | HivisionIDPhotos 代码 (`src/`) + 模型权重 + pip 缓存 — 在 `/Development` 独立盘，不在仓库内 |
| `comfyui_workdir` | `./data/comfyui_workdir` | ComfyUI 状态 |
