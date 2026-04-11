# Phase 2 — 音视频翻译 + Web UI + GPU 控制面板

> 状态：⏳ 待执行 | 计划开始时间：待用户指示
> **索引：** [← progress.md（英文）](../../../en/2-progress/progress.md) | [英文版 →](../../../en/2-progress/phases/phase2/plan.md)

---

## 目标

本阶段扩展平台，添加以下三项能力：
1. **音视频字幕生成与翻译** — 完全自托管，不依赖任何外部 API
2. **统一 Web UI** — 多页面响应式界面，支持手机、平板、电脑访问
3. **手动 GPU 控制面板** — 实时查看哪个容器占用显卡、手动启停服务

自动 GPU 切换（Orchestrator 调度器）延迟到 Phase 3 实现。

---

## 字幕策略 — 双轨流水线

优先使用最快的方式，仅在必要时才降级到本地语音识别（ASR）。

```
输入：视频文件 或 YouTube 链接
       ↓
[轨道 A] yt-dlp：尝试拉取已有 YouTube 字幕
       ↓ 找到字幕 → 跳过 ASR，直接进入翻译（秒级，无需 GPU）
       ↓ 无字幕（本地文件，或 YouTube 无字幕）
[轨道 B] ffmpeg：从视频提取音频
       ↓
       Whisper STT（本地 GPU，faster-whisper large-v3）→ 转录文本
       ↓
[两条轨道在此汇合]
       LiteLLM :4000 → Qwen 14B → 翻译为目标语言
       ↓
输出：.srt / .vtt / 纯文本
```

**为什么选这个顺序：**
- YouTube 字幕（存在时）几乎是即时的，且无需 GPU
- 只有在没有现成字幕时才调用 Whisper
- 这与 Grok 网页版的处理方式高度吻合（拉取 YouTube CC，而非跑 ASR）

---

## 整体架构

```
用户（浏览器——手机 / 平板 / 电脑）
       ↓ HTTPS / HTTP
  ai_webapp :8080  （FastAPI + HTML/CSS — 响应式，移动端优先）
       ├── /             → 首页：服务列表 + GPU 状态小组件
       ├── /subtitle     → 字幕生成（YouTube 链接 或 文件上传）
       ├── /translate    → 文本翻译
       ├── /gpu          → GPU 控制面板（手动启停 + 显存监控）
       └── /status       → JSON API，供 UI 组件轮询状态
       ↓
  [yt-dlp]  ←  YouTube 链接优先尝试
       ↓ fallback
  ai_whisper :9998  （faster-whisper，GPU）
       ↓
  ai_litellm :4000  （LiteLLM 网关 → Qwen 14B）
```

所有容器运行在 `ai_paas_network`。

---

## Web UI 设计原则

- **60分界面**：功能完整，不追求美观。稳定、少 bug 优先于视觉效果。
- **响应式 / 移动端优先**：使用 CSS flexbox/grid，单断点 768px。
  - 竖屏手机：单列堆叠布局
  - 平板 / 桌面：双列或侧边栏布局
- **不用重型前端框架**：原生 HTML + Vanilla JS + 极简 CSS。零构建步骤。
- **加载速度快**：不依赖外部 CDN（如需引入关键 CSS，内联嵌入）。
- **单容器**：`ai_webapp` 同时承载 HTML 页面和后端 API 路由。

---

## GPU 控制面板（步骤 2.6）

访问地址：`/gpu`。功能：

| 功能 | 实现方式 |
|---|---|
| 显示活跃容器 + 状态 | 通过 Docker SDK 调用 `docker ps` |
| 显示当前显存占用 | `nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader` |
| 启动 / 停止单个容器 | Docker SDK `container.start()` / `container.stop()` |
| 一键"切换到视觉层" | 停止 `ai_vllm` + `ai_whisper`；视觉容器手动管理（Phase 2 阶段） |
| 每 10 秒自动刷新 | JS `setInterval` 轮询 `/status` 端点 |

> ⚠️ 自动层切换（Orchestrator）不在 Phase 2 范围内，延迟到 Phase 3。
> Phase 2 的手动面板提供完整的可视化和控制能力，Orchestrator 将在其基础上构建自动化层。

---

## 显存预算

| 组件 | 显存占用 |
|---|---|
| vLLM（Qwen 14B，`gpu_memory_utilization=0.7`） | ~17 GB |
| Whisper large-v3（faster-whisper） | ~3–4 GB |
| **合计** | **~20–21 GB / 24 GB** |

✅ 可行。如果出现显存压力：先将 `gpu_memory_utilization` 降到 `0.6`（约 14.4 GB）。

---

## 选用镜像

| 服务 | 镜像 | 备注 |
|---|---|---|
| Whisper | `ghcr.io/speaches-ai/speaches:latest-cuda` | ⚠️ repo 已改名，见下方调研日志 |
| Web App | 自定义 Dockerfile（Python 3.12-slim + FastAPI + yt-dlp + ffmpeg） | 本地构建，存入 Harbor |

---

## 🔍 技术调研日志（AI 执行思路记录）

> **这一节专门给人类看。** 记录 AI 每一步的决策依据、搜索过程、发现了什么、为什么这样选。
> 目的：让你随时知道 AI 在干什么，不是黑箱。

---

### Step 2.2 执行思路（2026-03-30）

**出发点：原 plan 里写的镜像是 `fedirz/faster-whisper-server:latest-cuda`**

原 Phase 2 计划（写于 2026-03-22）指定了这个镜像。但 plan 同时标注了一条风险：
> "执行前需对照 `fedirz/faster-whisper-server` README 核实实际环境变量名"

所以在动 docker-compose 之前，我先去核实。

---

**发现 1：repo 已经改名了**

访问 `https://github.com/fedirz/faster-whisper-server` → 页面自动重定向到 `https://github.com/speaches-ai/speaches`。

项目已更名为 **speaches**，不再叫 faster-whisper-server。这意味着：
- 原镜像名 `fedirz/faster-whisper-server` 可能已停止更新
- 正确的新镜像是 `ghcr.io/speaches-ai/speaches:latest-cuda`
- 功能扩展了（不只 STT，还加了 TTS、VAD），但 `/v1/audio/transcriptions` 端点仍在

**决策**：用新镜像 `ghcr.io/speaches-ai/speaches:latest-cuda`，不用旧名字。

---

**发现 2：环境变量名与原 plan 不符**

原 plan 草稿写的是 `WHISPER__MODEL=large-v3`。

查阅 speaches 官方文档（`speaches.ai/configuration/`）后发现：

| 原 plan 写的 | 实际正确的 |
|---|---|
| `WHISPER__MODEL=large-v3` | **不存在这个变量** |
| （无）| `PRELOAD_MODELS=["Systran/faster-whisper-large-v3"]`（JSON 格式，HuggingFace model ID）|
| （无）| `WHISPER__INFERENCE_DEVICE=cuda` |
| （无）| `WHISPER__COMPUTE_TYPE=float16` |

模型必须用 HuggingFace 的完整 ID：`Systran/faster-whisper-large-v3`，不是简写 `large-v3`。
模型权重下载到容器内的 `/home/ubuntu/.cache/huggingface/hub`，需要挂载 named volume 持久化。

**决策**：使用正确的变量名，挂载 `whisper_model_cache` named volume 避免每次重启重新下载。

---

**发现 3：需要先测小模型验证 CUDA 兼容性**

按照 plan 的风险缓解策略（"先用小模型测试，再加载 large-v3"），我用 `Systran/faster-whisper-tiny` 先跑一遍测试容器，验证：
1. `ghcr.io/speaches-ai/speaches:latest-cuda` 镜像能在 CUDA 13 环境下启动
2. GPU 透传配置正确
3. `/health` 端点可达

测试命令（不影响现有 vLLM）：
```bash
docker run --rm --gpus all \
  -e WHISPER__INFERENCE_DEVICE=cuda \
  -e WHISPER__COMPUTE_TYPE=float16 \
  -e PRELOAD_MODELS='["Systran/faster-whisper-tiny"]' \
  -p 9999:8000 \
  ghcr.io/speaches-ai/speaches:latest-cuda
```

镜像体积较大（CUDA 基础层），首次 pull 需要几分钟。

---

**当前状态（截至本文更新时）**

- [x] 核实镜像名、环境变量 ✅（见"发现 1/2"）
- [x] 更新 `docker-compose.yml` 使用正确配置 ✅
- [x] 小模型 CUDA 兼容性测试 ✅（tiny 模型 0.86s 加载，`/health` = OK）
- [x] large-v3 模型下载 ✅（`POST /v1/models/Systran%2Ffaster-whisper-large-v3`）
- [x] VRAM 共存验证 ✅

**VRAM 测试结果（2026-03-30）：**

| 状态 | VRAM 已用 | 剩余 |
|---|---|---|
| 基线（仅 vLLM） | 17960 MiB | 6166 MiB |
| large-v3 加载峰值 | 22017 MiB | 2108 MiB |
| 稳态（TTL 卸载后） | 18231 MiB | 5894 MiB |

**关键发现**：speaches 默认 `ttl=300`（5分钟无请求自动从显存卸载模型）。这意味着：
- 实际工作时（处理转录）峰值约 22 GB，仍在 24 GB 以内 ✅
- 空闲时几乎不占额外显存，与 vLLM 长期共存无问题 ✅
- 下载 API：`POST /v1/models/Systran%2Ffaster-whisper-large-v3`（第一次启动时需手动调用一次，之后模型缓存在 named volume 里）

**发现 3：`PRELOAD_MODELS` 环境变量实际上不会自动触发下载**

原以为 `PRELOAD_MODELS=["Systran/faster-whisper-large-v3"]` 可以在启动时自动下载模型，但实测发现该变量只是配置记录，实际下载仍需手动调用 API。已在 docker-compose.yml 注释里说明。

---

**如果你想知道某个决策为什么这样做，直接问我**。我会在这里补充记录。

---

## 步骤计划

| 步骤 | 描述 | 状态 | Commit |
|---|---|---|---|
| **2.1** | 编写 Phase 2 计划（本文件） | ✅ `b8be598` | `b8be598` |
| **2.2** | 将 Whisper 服务添加到 `docker-compose.yml`；测试与 vLLM 的显存共存 | ✅ 完成 | `ce3095a`+本次 |
| **2.3** | 在 `litellm_config.yaml` 添加 Whisper 路由；重启 LiteLLM；验证 `/v1/audio/transcriptions` | ✅ 完成 | 本次 |
| **2.4** | 构建 Web App Dockerfile（FastAPI + yt-dlp + ffmpeg）；添加到 `docker-compose.yml` | ✅ 完成 | 本次 |
| **2.5** | 实现字幕流水线：yt-dlp → fallback Whisper → LiteLLM 翻译 | ✅ 完成 | 本次 |
| **2.6** | 实现 GPU 控制面板（`/gpu` 页面 + `/status` API + Docker SDK 集成） | ✅ 完成 | 本次 |
| **2.7** | 实现其余 Web UI 页面：`/`、`/translate`；应用响应式 CSS | ✅ 完成 | 本次 |
| **2.8** | 端到端测试：YouTube 链接 → 字幕；本地文件 → 字幕；GPU 面板启停 | ⬜ 待执行 | — |
| **2.9** | 更新 `codebase_map.md`，补充所有新容器和端点 | ⬜ 待执行 | — |

---

## 配置草稿（步骤 2.2–2.4 执行时使用）

**`docker-compose.yml` — Whisper 新增：**
```yaml
ai_whisper:
  image: fedirz/faster-whisper-server:latest-cuda
  container_name: ai_whisper
  ports:
    - "9998:8000"
  environment:
    - WHISPER__MODEL=large-v3
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
  networks:
    - ai_paas_network
  restart: unless-stopped
```

**`docker-compose.yml` — Web App 新增：**
```yaml
ai_webapp:
  build: ./services/webapp
  container_name: ai_webapp
  ports:
    - "8080:8080"
  environment:
    - LITELLM_BASE_URL=http://ai_litellm:4000/v1
    - LITELLM_API_KEY=${WEBAPP_LITELLM_KEY}
    - WHISPER_BASE_URL=http://ai_whisper:8000/v1
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro   # GPU 控制面板需要 Docker API
  networks:
    - ai_paas_network
  restart: unless-stopped
```

**`litellm_config.yaml` — Whisper 路由新增：**
```yaml
- model_name: whisper
  litellm_params:
    model: whisper/large-v3
    api_base: http://ai_whisper:8000/v1
```

> ⚠️ 以上均为草稿配置，在 Step 2.2 执行前不要应用。
> 执行前需对照 `fedirz/faster-whisper-server` README 核实实际环境变量名。

---

## 执行前待确认问题

- [ ] 确认 `fedirz/faster-whisper-server` GPU 透传语法（CUDA 12 vs 13 兼容性）
- [ ] 确认模型选择的环境变量名（可能不是 `WHISPER__MODEL`）
- [ ] 确认 Docker socket 挂载安全性（只读 `:ro` + 容器名白名单）
- [ ] 确定 TTS 输出是否在 Phase 2 范围内，还是推迟到 Phase 3

---

## 风险

| 风险 | 缓解措施 |
|---|---|
| Whisper large-v3 引起显存溢出 | 启动后监控 `nvidia-smi`；如需降级到 `medium` |
| faster-whisper 与 CUDA 13 兼容性未知 | 先用小模型测试，再加载 large-v3 |
| ffmpeg 不在 Web App 容器中 | 在 Dockerfile 中显式包含 |
| Docker socket 安全性（GPU 面板） | 只读挂载 `:ro`；仅允许对已知容器名执行启停（白名单） |
| yt-dlp YouTube 频率限制 / 格式变更 | 固定 yt-dlp 版本；在 UI 中添加清晰的降级错误提示 |
