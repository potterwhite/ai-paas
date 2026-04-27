# Vault RAG — Obsidian 知识库 AI 查询系统

> **Status:** Phase 3 Completed — 2026-04-27
> **Phase:** Phase 6 (Vault RAG)
> **Author:** Claude Code

---

## 愿景

让 AI 能够：
1. **读取** Vault 中的笔记，回答基于个人知识库的问题
2. **写入** AI 生成的分析/回答回 Vault

同时预留 RBAC 权限扩展接口。

---

## 1. 架构设计

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    ai_webapp (8888)                      │
│                    — 仅 UI                              │
└──────────────────────┬────────────────────────────────┘
                       │ HTTP API
┌──────────────────────▼────────────────────────────────┐
│                   ai_rag (xxxx)                           │
│                   — Vault RAG 服务（新容器）             │
│                                                          │
│  /v1/vault/query  · 查询 Vault                          │
│  /v1/vault/write  · 写入 Vault                         │
│  /v1/vault/index  · 重建索引                           │
└──────────────────────┬────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────┐
│                 ai_router (4000)                          │
│                 — LLM 推理                              │
└─────────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────┐
│                ai_vllm_qwen (9997)                        │
│                — Qwen 2.5 32B                            │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 容器间通信

- 使用 Docker 默认网络，容器名作为 hostname
- 通信方式：HTTP REST API
- 容器名：`ai_rag` → `http://ai_rag:xxxx/v1/vault/*`

---

## 2. RAG 原理

### 2.1 什么是 RAG

**Retrieval-Augmented Generation** — 检索增强生成

```
用户提问: "我上次的项目计划是什么？"
    │
    ▼
┌─────────────────┐
│  Embedding 模型  │ ← 把文字转成数字向量
│  (bge-small-zh)  │
└────────┬────────┘
         │  向量
         ▼
┌─────────────────┐
│  向量数据库      │ ← 找最相关的文档
│  (ChromaDB)      │
└────────┬────────┘
         │  相关文档
         ▼
┌─────────────────┐
│     vLLM         │ ← 根据上下文生成回答
│  (Qwen 2.5)      │
└─────────────────┘
```

### 2.2 Vault 在 RAG 中的角色

| 组件 | Vault 对应 |
|------|-----------|
| 原始数据 | `/ObsidianVault/*.md` 文件（保持 Markdown 不变） |
| 向量索引 | ChromaDB 数据库（内容的"数字指纹"） |
| 检索结果 | 相关的 .md 文件路径 |

**关键点**：原始 Markdown 文件不动，只是多了一个向量索引。

---

## 3. 组件设计

### 3.1 新增服务：ai_rag

```
services/rag/
├── main.py              # FastAPI 入口
├── rag_engine.py        # RAG 核心逻辑
├── embedding.py         # Embedding 模型调用
├── vault_writer.py     # 写回 Vault
├── auth.py             # API Key 验证（预留 RBAC）
├── config.py          # 配置
├── requirements.txt   # 依赖
└── Dockerfile         # 构建
```

### 3.2 API 接口

#### 查询接口

```
POST /v1/vault/query
Authorization: Bearer <api_key>

{
  "query": "我上次项目计划的要点是什么？",
  "top_k": 5,
  "loa_required": null  // 预留，null=不限制
}

Response:
{
  "answer": "根据你的笔记，项目计划的要点是...",
  "sources": [
    {
      "path": "PARA/Projects/项目A/计划.md",
      "relevance": 0.85,
      "snippet": "...相关片段..."
    }
  ]
}
```

#### 写入接口

```
POST /v1/vault/write
Authorization: Bearer <api_key>

{
  "query": "项目计划的要点",
  "ai_content": "# AI 分析\n\n## 问题\n项目计划的要点是什么？\n\n## 回答\n...",
  "mode": "new",         // "new"=新文件, "append"=追加到现有
  "target_path": null     // null=自动生成文件名
}

Response:
{
  "path": "PARA/Inbox/AI/2026-04-26_分析_项目计划.md",
  "success": true
}
```

#### 索引管理

```
POST /v1/vault/index/rebuild
Authorization: Bearer <sk-admin-key>

Response:
{
  "status": "rebuilding",
  "documents_indexed": 0
}
```

### 3.3 Embedding 模型选择

| 模型 | 大小 | 说明 |
|------|------|------|
| `bge-small-zh-v1.5` | ~70MB | 推荐：体积小、中文效果好 |
| `m3e-base` | ~400MB | 更精确，但更大 |

- 使用本地部署（`sentence-transformers`）
- **模型存储**：`${MODELS_PATH}/embedding/`（与 vLLM 模型同 HDD）
- GPU 资源充足时在 RAG 容器内运行
- 资源不足时可调用云端 API

### 3.4 向量数据库

| 方案 | 说明 |
|------|------|
| **ChromaDB** | 推荐：轻量、支持本地、内置 SQLite 后端 |
| Qdrant | 更强大，但需要额外容器 |

- **持久化存储**：`./data/rag_chroma`（NVMe，与 router_db 同一位置）

---

## 4. 数据模型

### 4.1 Vault 索引结构

```python
# ChromaDB Collection
{
    "id": "path/to/note.md",           # 文档路径（唯一ID）
    "embedding": [0.1, -0.3, ...],    # 向量
    "document": "...全文内容...",       # 原始文本
    "metadata": {
        "path": "path/to/note.md",
        "title": "文档标题",
        "tags": ["项目", "计划"],
        "loa_min": 1,                  # 预留：最低 LOA 要求
        "mtime": 1745689200
    }
}
```

### 4.2 API Keys 表（预留 RBAC）

```sql
-- 扩展现有 router DB
CREATE TABLE vault_api_keys (
    id INTEGER PRIMARY KEY,
    api_key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    loa_level INTEGER DEFAULT 1,  -- 1-5, 预留
    quota_daily INTEGER DEFAULT 100,
    created_at TIMESTAMP DEFAULT NOW,
    last_used TIMESTAMP
);
```

### 4.3 Vault 文档 LOA 标记（预留）

```markdown
---
title: "敏感项目A"
tags: ["项目", "机密"]
loa_min: 3  -- 需要 LOA >= 3 才能访问
---

# 敏感项目 A

...
```

---

## 5. 写入格式

### 5.1 新建文件格式

```markdown
---
ai-generated: true
source-query: "项目计划的要点是什么？"
created: 2026-04-26T20:00:00+08:00
source-docs:
  - "[[PARA/Projects/项目A/计划.md]]"
  - "[[PARA/Resources/项目.md]]"
---

# AI 分析：项目计划的要点

## 问题
项目计划的要点是什么？

## 回答
根据笔记分析，核心要点是...

## 参考文档
- [[PARA/Projects/项目A/计划.md]]
- [[PARA/Resources/项目.md]]
```

### 5.2 追加模式

当 `mode=append` 时，将内容追加到现有笔记末尾：

```markdown
---

## AI 分析 (2026-04-26)

[AI 生成的内容]

---
```

---

## 6. 部署设计

### 6.1 docker-compose.yml 新增服务

```yaml
rag:
  build: ./services/rag
  container_name: ai_rag
  restart: unless-stopped
  ports:
    - "8081:8081"
  volumes:
    - ${VAULT_PATH:-./vault}:/vault:ro
    - ./data/rag_chroma:/db/chroma
    - ${MODELS_PATH:-./models}:/models:ro
  environment:
    - RAG_PORT=8081
    - CHROMA_DB_PATH=/db/chroma
    - EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
    - VAULT_PATH=/vault
    - ROUTER_BASE_URL=http://ai_router:4000
    - ROUTER_API_KEY=${ROUTER_API_KEY}
  depends_on:
    - router
  networks:
    - default
```

### 6.2 环境变量

```bash
# .env 新增
VAULT_PATH=/Development/backup/PARA-Vault
RAG_PORT=8081
MODELS_PATH=/Development/docker/docker-volumes/ai_paas
```

---

## 7. 权限设计（RBAC 预留）

### 7.1 LOA 级别定义

| LOA | 名称 | 说明 |
|-----|------|------|
| 1 | Public | 公开信息 |
| 2 | Internal | 内部资料 |
| 3 | Confidential | 机密资料 |
| 4 | Restricted | 严格限制 |
| 5 | Top Secret | 最高机密 |

### 7.2 权限检查流程

```
用户请求 /v1/vault/query
        │
        ▼
┌───────────────────┐
│ 验证 API Key      │ ──失败──→ 401 Unauthorized
└────────┬──────────┘
         │ 成功
         ▼
┌───────────────────┐
│ 获取用户 LOA Level │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│ 检索相关文档      │
│ 过滤 loa_min >    │
│ 用户 LOA 的文档   │
└────────┬──────────┘
         │
         ▼
返回过滤后的结果
```

### 7.3 权限扩展点

当前默认：`loa_min=1` 对所有文档，暂不限制。

后期改造：
1. 在文档 frontmatter 添加 `loa_min: N`
2. 在 `vault_api_keys` 表添加用户 LOA
3. 在查询时过滤 `doc.loa_min <= user.loa_level`

---

## 8. 实现计划

### 8.1 Phase 1：基础版（当前设计）

- [x] 新建 `services/rag/` 服务
- [x] 实现 `POST /v1/vault/query`
- [x] 实现 `POST /v1/vault/write`
- [x] 集成 vLLM 生成回答
- [x] 挂载 Vault volume
- [x] 文档和测试

### 8.2 Phase 2：索引管理

- [x] `POST /v1/vault/index/rebuild`
- [x] 自动增量索引
- [x] 健康检查端点

### 8.3 Phase 3：RBAC 权限（预留）

- [x] 添加 `loa_min` frontmatter 解析
- [x] 扩展 `vault_api_keys` 表
- [x] 实现权限过滤逻辑
- [ ] 管理 API（LOA 配置）

---

## 9. 依赖

- Python 3.11+
- FastAPI
- ChromaDB
- sentence-transformers（Embedding 模型）
- httpx（调用 Router）
- aiofiles（非阻塞文件读取）

---

## 10. FAQ

### Q: 为什么不用 Obsidian 插件？

A: Obsidian 插件只能在 Obsidian 应用内使用。我们需要通过 API 对外提供服务。

### Q: 可以用哪些现有的向量数据库？

A: 推荐 ChromaDB（轻量），也可以用 Qdrant（更强��）。

### Q: Embedding 模型一定要本地部署吗？

A: 可以用云端 API（OpenAI text-embedding-3-small），但本地模型更隐私、无 API 费用。

### Q: 容器间通信效率如何？

A: Docker 网络延迟 < 1ms，与本地进程间通信无明显差异。

---

## 11. 参考资料

- [ChromaDB 文档](https://docs.trychroma.com/)
- [BGE Embedding 模型](https://huggingface.co/BAAI/bge-small-zh-v1.5)
- [RBAC 维基百科](https://en.wikipedia.org/wiki/Role-based_access_control)