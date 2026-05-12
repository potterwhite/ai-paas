# ai-paas 系统架构详解

> 最后更新：2026-05-12

---

## 目录

1. [整体架构概览](#整体架构概览)
2. [容器职责划分](#容器职责划分)
3. [数据流动详解](#数据流动详解)
4. [内部编程模型](#内部编程模型)
5. [Wiki 系统深度解析](#wiki-系统深度解析)
6. [故障排查指南](#故障排查指南)

---

## 整体架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户浏览器                                      │
│                     http://192.168.0.19:8888                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ai_webapp (端口 8888)                              │
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   首页 /    │  │  Wiki /wiki │  │ 知识库      │  │ GPU /gpu    │        │
│  │   显存面板  │  │  知识问答   │  │ /knowledge  │  │ 模型管理    │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│         │                │                │                │                │
│         └────────────────┴────────────────┴────────────────┘                │
│                                    │                                        │
│                              API 代理层                                      │
│                     /api/wiki-query → ai_rag:8081                           │
│                     /api/knowledge-query → ai_rag:8081                      │
│                     /v1/chat/* → ai_router:4000                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│      ai_router (端口 4000)       │  │       ai_rag (端口 8081)         │
│                                  │  │                                  │
│  OpenAI 兼容 API 网关            │  │  RAG + Wiki 知识引擎             │
│  ┌────────────────────────────┐  │  │  ┌────────────────────────────┐  │
│  │ /v1/chat/completions       │  │  │  │ /v1/wiki/query             │  │
│  │ /v1/audio/transcriptions   │  │  │  │ /v1/wiki/ingest            │  │
│  │ /v1/gpu                    │  │  │  │ /v1/vault/query            │  │
│  │ /v1/models                 │  │  │  │ /v1/vault/write            │  │
│  └────────────────────────────┘  │  │  └────────────────────────────┘  │
│           │                      │  │           │                      │
│           ▼                      │  │           ▼                      │
│  ┌────────────────────────────┐  │  │  ┌────────────────────────────┐  │
│  │    模型注册表 + 路由       │  │  │  │   ChromaDB 向量数据库      │  │
│  │    VLLM_MODELS dict        │  │  │  │   BGE embedding            │  │
│  └────────────────────────────┘  │  │  └────────────────────────────┘  │
└──────────────────────────────────┘  └──────────────────────────────────┘
           │                                   │
           ▼                                   ▼
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│  ai_vllm_qwen (端口 9997→8000)  │  │      Vault 文件系统              │
│                                  │  │  /vault/_wiki/ (Wiki 页面)       │
│  vLLM 推理引擎                   │  │  /vault/_schema/ (指令模板)      │
│  Qwen 2.5 32B AWQ 4-bit         │  │  /vault/**/*.md (源文档)         │
│  GPU 显存 ~22 GB                 │  │                                  │
└──────────────────────────────────┘  └──────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│  ai_whisper (端口 9998→8000)     │
│                                  │
│  Whisper STT 语音转文字          │
│  faster-whisper-large-v3         │
│  GPU 显存 ~3-4 GB                │
└──────────────────────────────────┘
```

---

## 容器职责划分

### 1. ai_webapp — 用户界面层

**职责**：提供 Web UI，代理 API 请求

**技术栈**：Python FastAPI + 内联 HTML/CSS/JS（无前端框架）

**核心文件**：`services/webapp/main.py`（~4900 行）

**做了什么**：
- 渲染所有前端页面（首页、Wiki、知识库、GPU、模型管理等）
- 将用户操作转换为 API 调用
- 代理请求到后端服务（Router、RAG）
- 处理错误并展示给用户

**不做什么**：
- 不执行 LLM 推理
- 不存储数据
- 不管理 GPU

**关键代码位置**：
```python
# 页面路由定义（内联 HTML）
@app.get("/wiki", response_class=HTMLResponse)     # 第 1091 行
@app.get("/knowledge", response_class=HTMLResponse) # 第 1012 行

# API 代理层
@app.post("/api/wiki-query")       # 第 1386 行 → 代理到 ai_rag:8081/v1/wiki/query
@app.get("/api/wiki-status")       # 第 1427 行 → 代理到 ai_rag:8081/v1/wiki/status
@app.post("/api/wiki-config")      # 第 1458 行 → 代理到 ai_rag:8081/v1/wiki/config
@app.post("/api/knowledge-query")  # 第 1359 行 → 代理到 ai_rag:8081/v1/vault/query
```

---

### 2. ai_router — API 网关层

**职责**：统一 LLM API 接口，管理 GPU 资源

**技术栈**：Python FastAPI + Celery + Redis + SQLite

**核心文件**：`services/router/app/main.py`

**做了什么**：
- 提供 OpenAI 兼容的 `/v1/chat/completions` 接口
- 动态路由请求到当前活跃的 vLLM 实例
- 管理 vLLM 容器的启停（通过 Docker SDK）
- 管理 GPU 模式切换（LLM vs ComfyUI）
- 模型注册表和切换
- 异步任务队列（Celery）

**不做什么**：
- 不直接处理用户界面
- 不执行 RAG/Wiki 逻辑
- 不管理文件系统

**关键 API**：
```
POST /v1/chat/completions     → 转发到活跃的 ai_vllm_qwen 或 ai_vllm_gemma
POST /v1/audio/transcriptions → 转发到 ai_whisper
GET  /v1/gpu                  → 查询 GPU 状态
POST /v1/models/switch        → 切换模型（停旧容器、启新容器）
```

**内部编程模型**：
```python
# Router 核心：模型注册表
VLLM_MODELS = {
    "qwen": {
        "container": "ai_vllm_qwen",
        "profile": "llm-qwen",
        "model_path": "/models/qwen2.5-32b-instruct-awq",
        ...
    },
    "gemma": {
        "container": "ai_vllm_gemma",
        "profile": "llm-gemma",
        ...
    }
}

# 路由逻辑：找到活跃模型 → 转发请求
async def chat_completions(request):
    active_model = detect_active_vllm()  # 检查哪个 vLLM 容器在运行
    response = await forward_to_vllm(active_model, request)
    return response
```

---

### 3. ai_rag — 知识引擎层

**职责**：RAG 查询、Wiki 知识问答、文档管理

**技术栈**：Python FastAPI + ChromaDB + BGE embedding + httpx

**核心文件**：`services/rag/app/main.py`

**做了什么**：
- **传统 RAG**：向量检索 + LLM 生成回答
  - `/v1/vault/query` — 查询 Vault 文档
  - `/v1/vault/write` — 写回 Vault
  - `/v1/vault/index/rebuild` — 重建向量索引
- **Wiki 系统**：结构化知识问答
  - `/v1/wiki/query` — Wiki 查询（LLM 选页 + 生成答案）
  - `/v1/wiki/ingest` — 文档入库（源文档 → 结构化 Wiki 页面）
  - `/v1/wiki/ingest/batch` — 批量入库
  - `/v1/wiki/status` — 查询状态
  - `/v1/wiki/config` — 更新配置
  - `/v1/wiki/lint` — 结构校验

**不做什么**：
- 不直接面对用户
- 不管理 GPU 容器
- 不提供 Web UI

**关键依赖**：
```
ai_rag ──调用 LLM──→ ai_router:4000 ──转发──→ ai_vllm_qwen:8000
    │
    └──读写文件──→ /vault/ (挂载的 Vault 目录)
    │
    └──存储向量──→ /db/chroma/ (ChromaDB 持久化)
```

---

### 4. ai_vllm_qwen / ai_vllm_gemma — LLM 推理层

**职责**：执行 LLM 推理，生成文本

**技术栈**：vLLM + CUDA

**做了什么**：
- 加载模型权重到 GPU 显存
- 提供 OpenAI 兼容的 `/v1/chat/completions` 接口
- 执行 token 生成（推理）

**不做什么**：
- 不处理业务逻辑
- 不管理文件
- 不提供 Web UI

**关键约束**：
- 单 GPU 同时只能运行一个 vLLM 实例
- Qwen 32B 需要 ~22 GB 显存
- 模型 context length 限制（Qwen: 8192 tokens）

---

### 5. ai_whisper — 语音转文字层

**职责**：音频转录

**技术栈**：faster-whisper + CUDA

**做了什么**：
- 接收音频文件
- 返回文字转录结果

---

### 6. ai_router_redis — 缓存/队列层

**职责**：Celery 消息队列 + 结果存储

**技术栈**：Redis 7

**做了什么**：
- 为 Celery 提供 broker（任务队列）
- 为 Celery 提供 result backend（结果存储）
- 缓存热点数据

---

## 数据流动详解

### 流程 1：用户查询 Wiki

```
用户浏览器                    ai_webapp                   ai_rag                    ai_router               ai_vllm_qwen
    │                            │                          │                          │                          │
    │  1. POST /api/wiki-query   │                          │                          │                          │
    │  {"question": "什么是X"}   │                          │                          │                          │
    │ ─────────────────────────> │                          │                          │                          │
    │                            │                          │                          │                          │
    │                            │  2. POST /v1/wiki/query  │                          │                          │
    │                            │  {"question": "什么是X"} │                          │                          │
    │                            │ ────────────────────────> │                          │                          │
    │                            │                          │                          │                          │
    │                            │                          │  3. 读取 _schema/query.md │                          │
    │                            │                          │  读取 _wiki/index.md      │                          │
    │                            │                          │  读取 _wiki/hot.md        │                          │
    │                            │                          │ ─────────┐                │                          │
    │                            │                          │          │                │                          │
    │                            │                          │ <────────┘                │                          │
    │                            │                          │  组装 prompt               │                          │
    │                            │                          │                          │                          │
    │                            │                          │  4. POST /v1/chat/completions (选页)                 │
    │                            │                          │  model: "qwen"                                       │
    │                            │                          │  max_tokens: 500                                     │
    │                            │                          │ ───────────────────────────────────────────────────> │
    │                            │                          │                          │                          │
    │                            │                          │                          │  5. 转发到活跃 vLLM       │
    │                            │                          │                          │ ────────────────────────> │
    │                            │                          │                          │                          │
    │                            │                          │                          │  6. 返回选中的页面列表    │
    │                            │                          │                          │ <──────────────────────── │
    │                            │                          │ <──────────────────────── │                          │
    │                            │                          │                          │                          │
    │                            │                          │  7. 读取选中的 Wiki 页面   │                          │
    │                            │                          │ ─────────┐                │                          │
    │                            │                          │          │                │                          │
    │                            │                          │ <────────┘                │                          │
    │                            │                          │                          │                          │
    │                            │                          │  8. POST /v1/chat/completions (生成答案)             │
    │                            │                          │  model: "qwen"                                       │
    │                            │                          │  max_tokens: 1600                                    │
    │                            │                          │ ───────────────────────────────────────────────────> │
    │                            │                          │                          │                          │
    │                            │                          │                          │  9. 返回生成的答案        │
    │                            │                          │                          │ <──────────────────────── │
    │                            │                          │ <──────────────────────── │                          │
    │                            │                          │                          │                          │
    │                            │  10. 返回结果             │                          │                          │
    │                            │  {answer, citations}     │                          │                          │
    │                            │ <──────────────────────── │                          │                          │
    │ <────────────────────────── │                          │                          │                          │
    │  展示答案 + 引用来源        │                          │                          │                          │
```

**关键点**：
- Wiki 查询需要 **两次 LLM 调用**：选页 + 生成答案
- 每次 LLM 调用都经过 Router 转发到 vLLM
- 总耗时 = 选页时间 + 读文件时间 + 生成答案时间（通常 10-30 秒）

---

### 流程 2：Wiki 文档入库

```
用户/CLI                     ai_rag                    ai_router               ai_vllm_qwen
    │                          │                          │                          │
    │  1. POST /v1/wiki/ingest │                          │                          │
    │  {source_path: "xxx.md"} │                          │                          │
    │ ────────────────────────> │                          │                          │
    │                          │                          │                          │
    │                          │  2. 读取源文档             │                          │
    │                          │ ─────────┐                │                          │
    │                          │          │                │                          │
    │                          │ <────────┘                │                          │
    │                          │                          │                          │
    │                          │  3. 读取 _schema/ingest.md│                          │
    │                          │ ─────────┐                │                          │
    │                          │          │                │                          │
    │                          │ <────────┘                │                          │
    │                          │                          │                          │
    │                          │  4. POST /v1/chat/completions                        │
    │                          │  "请将以下文档转换为 Wiki 页面格式"                    │
    │                          │ ───────────────────────────────────────────────────> │
    │                          │                          │                          │
    │                          │                          │  5. 返回结构化 Wiki 页面   │
    │                          │                          │ <──────────────────────── │
    │                          │ <──────────────────────── │                          │
    │                          │                          │                          │
    │                          │  6. 写入 _wiki/xxx.md     │                          │
    │                          │ ─────────┐                │                          │
    │                          │          │                │                          │
    │                          │ <────────┘                │                          │
    │                          │                          │                          │
    │                          │  7. 更新 index.md         │                          │
    │                          │ ─────────┐                │                          │
    │                          │          │                │                          │
    │                          │ <────────┘                │                          │
    │  8. 返回成功              │                          │                          │
    │ <──────────────────────── │                          │                          │
```

---

### 流程 3：传统 RAG 查询（/knowledge）

```
用户浏览器                    ai_webapp                   ai_rag                    ai_router               ai_vllm_qwen
    │                            │                          │                          │                          │
    │  1. POST /api/knowledge-query                         │                          │                          │
    │  {"question": "什么是X"}   │                          │                          │                          │
    │ ─────────────────────────> │                          │                          │                          │
    │                            │                          │                          │                          │
    │                            │  2. POST /v1/vault/query │                          │                          │
    │                            │ ────────────────────────> │                          │                          │
    │                            │                          │                          │                          │
    │                            │                          │  3. ChromaDB 向量检索     │                          │
    │                            │                          │ ─────────┐                │                          │
    │                            │                          │          │                │                          │
    │                            │                          │ <────────┘                │                          │
    │                            │                          │  返回 top-k 相关文档片段   │                          │
    │                            │                          │                          │                          │
    │                            │                          │  4. POST /v1/chat/completions                        │
    │                            │                          │  "基于以下文档回答问题"    │                          │
    │                            │                          │ ───────────────────────────────────────────────────> │
    │                            │                          │                          │                          │
    │                            │                          │                          │  5. 返回答案              │
    │                            │                          │                          │ <──────────────────────── │
    │                            │                          │ <──────────────────────── │                          │
    │                            │                          │                          │                          │
    │                            │  6. 返回结果             │                          │                          │
    │                            │ <──────────────────────── │                          │                          │
    │ <────────────────────────── │                          │                          │                          │
```

**RAG vs Wiki 的区别**：
| 特性 | 传统 RAG | Wiki |
|------|----------|------|
| 检索方式 | 向量相似度搜索 | LLM 智能选页 |
| 数据格式 | 原始文档片段 | 结构化 Wiki 页面 |
| 质量 | 依赖 embedding 质量 | 更高（预处理 + 结构化） |
| 速度 | 较快（1 次 LLM 调用） | 较慢（2 次 LLM 调用） |
| 入库成本 | 低（只需 embedding） | 高（需要 LLM 处理） |

---

## 内部编程模型

### Webapp 编程模式

Webapp 使用 **内联 HTML** 模式，所有前端代码直接嵌入 Python 字符串：

```python
@app.get("/wiki", response_class=HTMLResponse)
async def wiki_page():
    body = """
<div class="card">
  <h2>Wiki 知识库</h2>
  <input type="text" id="wiki-query" placeholder="输入问题...">
  <button onclick="runWikiQuery()">查询</button>
  <div id="wiki-result"></div>
</div>

<script>
async function runWikiQuery() {
  const query = document.getElementById('wiki-query').value;
  const r = await fetch('/api/wiki-query', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question: query})
  });
  const d = await r.json();
  document.getElementById('wiki-result').innerHTML = d.answer;
}
</script>
"""
    return page("Wiki", "/wiki", body)
```

**特点**：
- 无前端构建工具（无 webpack/vite）
- JavaScript 直接写在 HTML 字符串中
- 通过 `fetch()` 调用后端 API
- 使用 CSS 变量实现主题切换

---

### RAG 编程模式

RAG 服务使用 **模块化** 模式：

```python
# main.py — 路由定义
@app.post("/v1/wiki/query")
async def wiki_query_endpoint(request: WikiQueryRequest):
    result = await wiki_query.query(request.question)
    return WikiQueryResponse(...)

# wiki_query.py — 查询引擎
class WikiQuery:
    async def query(self, question: str) -> WikiQueryResult:
        # 1. 读取 schema
        schema = await wiki_schema.get_schema("query", token_budget=1500)

        # 2. 读取索引
        index = await _read_file(wiki_path / "index.md")

        # 3. LLM 选页
        pages = await _select_pages(schema, question, index, hot)

        # 4. 读取页面内容
        wiki_pages = {p: await _read_file(vault / p) for p in pages}

        # 5. LLM 生成答案
        answer, citations = await _generate_answer(schema, question, wiki_pages)

        return WikiQueryResult(answer=answer, citations=citations)

# wiki_schema.py — Schema 管理
class WikiSchema:
    async def get_schema(self, operation: str, token_budget: int) -> str:
        content = await self._read_file(f"_schema/{operation}.md")
        return self.trim_to_budget(content, token_budget)
```

**特点**：
- 清晰的模块分工（main.py / wiki_query.py / wiki_schema.py）
- 使用 Pydantic 做数据验证
- 使用 httpx 异步调用 LLM
- 使用 aiofiles 异步读写文件

---

### Router 编程模式

Router 使用 **注册表 + 路由** 模式：

```python
# config.py — 模型注册表
VLLM_MODELS = {
    "qwen": {
        "container": "ai_vllm_qwen",
        "profile": "llm-qwen",
        "model_path": "/models/qwen2.5-32b-instruct-awq",
        "gpu_memory_utilization": 0.98,
        "max_model_len": 8192,
    },
    "gemma": {
        "container": "ai_vllm_gemma",
        "profile": "llm-gemma",
        ...
    }
}

# router_engine.py — 路由引擎
class RouterEngine:
    async def chat_completions(self, request):
        # 1. 检测活跃模型
        active_model = self.detect_active_model()

        # 2. 转发请求
        response = await self.forward_to_vllm(active_model, request)

        return response

    def detect_active_model(self):
        # 检查哪个 vLLM 容器在运行
        for name, config in VLLM_MODELS.items():
            if self.is_container_running(config["container"]):
                return name
        return None
```

---

## Wiki 系统深度解析

### Wiki 文件结构

```
/vault/
├── _schema/                    ← 指令模板（告诉 LLM 如何工作）
│   ├── query.md                ← 查询时的 system prompt
│   ├── ingest.md               ← 入库时的 system prompt
│   ├── lint.md                 ← 校验时的 system prompt
│   └── templates/              ← Wiki 页面模板
│       ├── entity.md
│       └── concept.md
│
├── _wiki/                      ← Wiki 页面（LLM 生成的结构化知识）
│   ├── index.md                ← 目录索引（所有页面的链接列表）
│   ├── hot.md                  ← 热缓存（最近使用的页面）
│   ├── log.md                  ← 操作日志
│   ├── entity/                 ← 实体页面
│   │   ├── xxx.md
│   │   └── yyy.md
│   └── concept/                ← 概念页面
│       ├── aaa.md
│       └── bbb.md
│
└── **/*.md                     ← 源文档（用户写的原始笔记）
```

### Wiki 查询流程详解

```
用户问题: "什么是 RAG？"

Step 1: 读取指令模板
├── 读取 _schema/query.md (1500 tokens)
└── 告诉 LLM: "你是一个 Wiki 助手，请根据以下页面回答问题..."

Step 2: 读取索引
├── 读取 _wiki/index.md (1348 tokens)
├── 读取 _wiki/hot.md (1551 tokens)
└── 索引内容: [RAG 概念](_wiki/concept/rag.md), [向量检索](_wiki/concept/vector-search.md), ...

Step 3: LLM 选页 (第一次 LLM 调用)
├── Prompt: schema + 问题 + 索引
├── max_tokens: 500
└── 返回: ["_wiki/concept/rag.md", "_wiki/concept/vector-search.md"]

Step 4: 读取选中的页面
├── 读取 _wiki/concept/rag.md
└── 读取 _wiki/concept/vector-search.md

Step 5: LLM 生成答案 (第二次 LLM 调用)
├── Prompt: schema + 问题 + 页面内容
├── max_tokens: 1600
└── 返回: "根据 [[RAG 概念]]，RAG 是... 根据 [[向量检索]]，..."

Step 6: 提取引用
├── 扫描答案中的 [[页面名]]
└── 返回: [{path: "_wiki/concept/rag.md", relevance: "primary"}, ...]
```

### Token 预算管理

Wiki 系统需要严格管理 token 使用，因为 Qwen 32B 的 context length 只有 8192 tokens。

```
总预算: 8192 tokens

分配:
├── Schema (指令模板): 1500 tokens
├── Index (目录索引): ~1500 tokens
├── Hot (热缓存): ~1500 tokens
├── Question (问题): ~100 tokens
├── Prompt overhead: ~200 tokens
└── Output (输出): 500 tokens (选页) 或 1600 tokens (生成答案)

选页时: 1500 + 1500 + 1500 + 100 + 200 + 500 = 5300 tokens ✓
生成时: 1500 + 页面内容 + 100 + 200 + 1600 = 变量
```

**当前问题**：
- index.md (3371 chars ≈ 1348 tokens) + hot.md (3878 chars ≈ 1551 tokens) 太大
- 加上 schema (1500 tokens) 和 prompt overhead，总输入接近 5000 tokens
- 如果页面内容较长，生成答案时可能超出 8192 限制

---

## 故障排查指南

### 问题 1: Wiki 查询返回 "LLM 后端不可用"

**症状**：点击查询按钮后，显示错误 "LLM 后端不可用"

**原因**：vLLM 容器未启动，或 token 超出模型限制

**排查步骤**：
```bash
# 1. 检查 vLLM 是否运行
docker ps | grep ai_vllm

# 2. 检查 vLLM 日志
docker logs ai_vllm_qwen --tail 50

# 3. 测试 LLM 是否可用
curl -X POST http://192.168.0.19:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-1234" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'

# 4. 检查 token 错误
# 如果返回 "maximum context length is 8192 tokens"，说明输入太长
```

**解决方案**：
- 如果 vLLM 未启动：`docker compose --profile llm-qwen up -d`
- 如果 token 超限：减少 `_wiki/index.md` 和 `_wiki/hot.md` 的内容，或调整 schema token 预算

---

### 问题 2: 点击 Wiki 链接返回 404

**症状**：访问 `http://192.168.0.19:4000/wiki` 返回 404

**原因**：Router 只处理 `/v1/*` API 路由，不处理前端页面

**解决方案**：
- 访问 `http://192.168.0.19:8888/wiki`（Webapp 端口）
- 或访问 `http://192.168.0.19:8888`（首页）

---

### 问题 3: Wiki 页面加载但点击无反应

**症状**：页面正常显示，但点击按钮没反应

**原因**：
1. 浏览器缓存了旧版本的 JavaScript
2. RAG 服务不可达，错误被静默吞掉

**排查步骤**：
```bash
# 1. 检查 RAG 服务
docker ps | grep ai_rag

# 2. 测试 RAG 端点
curl http://192.168.0.19:8081/v1/wiki/status

# 3. 测试 Webapp 代理
curl http://192.168.0.19:8888/api/wiki-status

# 4. 强制刷新浏览器 (Ctrl+Shift+R)
```

---

### 问题 4: 容器启动失败

**排查步骤**：
```bash
# 查看所有容器状态
docker ps -a

# 查看特定容器日志
docker logs ai_webapp --tail 100
docker logs ai_router --tail 100
docker logs ai_rag --tail 100

# 检查 GPU 使用情况
nvidia-smi

# 重启所有服务
docker compose down
docker compose up -d
```

---

### 问题 5: 模型切换失败

**症状**：切换模型后，LLM 仍然使用旧模型

**原因**：旧容器未完全停止，或新容器启动失败

**排查步骤**：
```bash
# 1. 检查所有 vLLM 容器
docker ps -a | grep vllm

# 2. 手动停止旧容器
docker stop ai_vllm_qwen

# 3. 启动新容器
docker compose --profile llm-gemma up -d vllm-gemma

# 4. 验证
curl http://192.168.0.19:4000/v1/models
```

---

## 附录：端口映射表

| 服务 | 容器内部端口 | 宿主机端口 | 用途 |
|------|-------------|-----------|------|
| ai_webapp | 8080 | 8888 | Web UI |
| ai_router | 4000 | 4000 | API 网关 |
| ai_rag | 8081 | 8081 | RAG/Wiki 引擎 |
| ai_vllm_qwen | 8000 | 9997 | LLM 推理（调试用） |
| ai_whisper | 8000 | 9998 | STT（调试用） |
| ai_comfyui | 8188 | 8188 | 视频生成（调试用） |

**访问方式**：
- 用户界面：`http://192.168.0.19:8888`
- LLM API：`http://192.168.0.19:4000/v1/chat/completions`
- RAG API：`http://192.168.0.19:8081/v1/vault/query`
- Wiki API：`http://192.168.0.19:8081/v1/wiki/query`
