# ai-paas

**单卡 GPU 自托管 AI 平台 — LLM 推理、语音识别、视频生成，全部通过一个 OpenAI 兼容 API 端点提供服务。**

> 零云成本。无 token 计费。数据不离本地。

[English →](../../README.md)

---

## 你能获得什么

- **一个 API 地址 + 一个 API Key** — 任何应用或 Agent 指向 `http://your-host:4000/v1` 即可使用，无需关心底层跑的是什么模型
- **LLM 推理** — Qwen 2.5 32B AWQ via vLLM，完整支持 Agent 工具调用循环
- **语音识别** — Whisper（faster-whisper large-v3），懒加载 + TTL 定时自动卸载
- **图像/视频生成** — ComfyUI，GPU 独占权由调度器自动管理
- **虚拟 Key 隔离** — 每个应用/Agent 获得独立 scoped key，主密钥仅管理员使用
- **用量追踪** — 每个 Key 的请求记录存储于 SQLite
- **Web 管理界面** — 字幕生成、文本翻译、GPU 控制面板、模型管理

全部以 Docker 容器运行，无裸机安装、无 Python 虚拟环境。

---

## 为什么不用 Ollama？

| 功能 | Ollama | ai-paas |
|---|:---:|:---:|
| OpenAI 兼容 API | ✅ | ✅ |
| 虚拟 API Key（按应用隔离） | ❌ | ✅ |
| 每个 Key 的用量追踪 | ❌ | ✅ |
| Agent 工具调用（已验证可用） | ⚠️ | ✅ |
| Whisper 语音识别同栈集成 | ❌ | ✅ |
| 图像/视频生成（ComfyUI） | ❌ | ✅ |
| AWQ 量化（节省显存） | ⚠️ | ✅ |
| 跨工作负载 GPU 调度 | ❌ | ✅ |

---

## 架构

```
你的应用 / AI Agent
        │  POST /v1/chat/completions
        │  Authorization: Bearer <api-key>
        ▼
┌──────────────────────────────────────┐
│  Router  :4000                       │
│  ├─ API key 鉴权 + 用量日志           │
│  ├─ GPU 调度（Celery + Redis）        │
│  ├─→ vLLM :8000  （LLM 推理）        │
│  └─→ Whisper :9998  （语音识别）      │
└──────────────────────────────────────┘

ComfyUI :8188  — GPU 独占，通过 WebUI 手动启停
WebUI   :8888  — 管理后台
```

### GPU 预算（RTX 3090 · 24 GB）

| 模式 | 活跃服务 | 显存占用 |
|---|---|---|
| 文本推理（默认） | vLLM 32B AWQ | ~22 GB |
| 文本 + 语音 | vLLM 14B + Whisper | ~17 + ~4 GB |
| 图像/视频生成 | ComfyUI（独占） | 最高 24 GB |

vLLM 和 ComfyUI 无法同时运行——GPU 调度器自动处理切换。

---

## 快速启动

**前置要求：** Docker + Docker Compose、NVIDIA GPU + Container Toolkit、模型权重文件。

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/ai-paas.git
cd ai-paas

# 2. 配置密钥
cp .env.example .env
# 编辑 .env，设置你自己的密码和 API Key

# 3. 放置模型权重
#    下载 Qwen2.5-32B-Instruct-AWQ，放入：
#    models/qwen2.5-32b-instruct-awq/

# 4. 启动全栈
docker compose up -d

# 5. 验证
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-1234" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"你好"}],"max_tokens":10}'
```

Web 管理界面：`http://localhost:8888`

---

## 服务与端口

| 服务 | 端口 | 用途 |
|---|---|---|
| Router（API 网关） | 4000 | OpenAI 兼容端点、key 鉴权、GPU 调度 |
| vLLM | 9997（仅调试） | LLM 推理——生产环境走 Router |
| Whisper | 9998 | 语音转文字（转录） |
| ComfyUI | 8188 | 图像/视频生成 |
| Web UI | 8888 | 管理后台 |

---

## 测试环境

| 组件 | 版本 |
|---|---|
| 操作系统 | Ubuntu 24.04 |
| GPU | NVIDIA RTX 3090 24 GB |
| NVIDIA 驱动 | 580.x |
| CUDA | 13.0 |
| Docker | 27.x + NVIDIA Container Toolkit |
| vLLM | 0.18.0 |

---

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/zh/1-for-ai/codebase_map.md`](1-for-ai/codebase_map.md) | 完整基础设施地图 — 所有容器、端口、配置值 |
| [`docs/zh/4-for-beginner/quick_start.md`](4-for-beginner/quick_start.md) | 新手首次部署手册 |
| [`docs/zh/3-highlights/architecture_vision.md`](3-highlights/architecture_vision.md) | 架构决策与理由 |

---

## License

MIT
