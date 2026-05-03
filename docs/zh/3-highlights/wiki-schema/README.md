# Wiki Schema — AI 知识管理行为规范

> 版本：v0.1.0（设计阶段）
> 日期：2026-05-03
> 目标模型：Qwen 32B AWQ（9600 token 上下文窗口）

---

## 这是什么

这套 Schema 文件定义了 LLM 如何管理你的 Obsidian 知识库。它们是纯 Markdown 文件，作为 LLM 的行为指令——告诉 LLM 如何入库新文档、如何回答查询、如何维护知识库健康。

灵感来源：[Karpathy 的 LLM Wiki 概念](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

## 三层架构

```
obsidian-nexus  →  模板层（Schema 模板，给社区分发）
ai-paas         →  引擎层（Wiki 引擎，读取 Schema 并调用 LLM）
PARA-Vault      →  数据层（你的 1800+ 篇文档 + AI 生成的 wiki 页面）
```

本目录的内容属于**模板层**。确认后会复制到 PARA-Vault 的 `_schema/` 目录供引擎使用。

## 文件清单

| 文件 | 用途 | 给谁读 |
|---|---|---|
| `ingest.md` | 入库规范：如何处理源文档、生成 wiki 页面 | LLM（通过引擎注入） |
| `query.md` | 查询规范：如何基于 wiki 页面回答问题 | LLM（通过引擎注入） |
| `lint.md` | 维护规范：如何检查 wiki 健康状态 | LLM（通过引擎注入） |
| `templates/entity.md` | 实体页模板（项目、工具、领域） | LLM（生成页面时参考） |
| `templates/concept.md` | 概念页模板（技术概念、方法论） | LLM（生成页面时参考） |
| `templates/source.md` | 源文档摘要模板 | LLM（生成页面时参考） |
| `templates/synthesis.md` | 综合分析模板 | LLM（生成页面时参考） |
| `templates/question.md` | 存档 Q&A 模板 | LLM（生成页面时参考） |

## Wiki 目录结构（运行时）

Schema 被引擎使用时，会在 PARA-Vault 中生成以下结构：

```
PARA-Vault/
├── 1_PROJECT/           ← 源文档（人写，AI 只读）
├── 2_AREA/              ← 源文档（人写，AI 只读）
├── 3_RESOURCE/          ← 源文档（人写，AI 只读）
├── 4_ARCHIVE/           ← 源文档（人写，AI 只读）
├── _schema/             ← Schema 文件（从本目录复制）
│   ├── ingest.md
│   ├── query.md
│   ├── lint.md
│   └── templates/
└── _wiki/               ← AI 生成的 wiki 页面（AI 写，人可编辑）
    ├── index.md         ← 目录索引（查询入口）
    ├── hot.md           ← 滚动热缓存（≤500 字）
    ├── log.md           ← 操作日志（只追加）
    ├── entity/          ← 实体页
    ├── concept/         ← 概念页
    ├── source/          ← 源文档摘要
    ├── synthesis/       ← 综合分析
    └── question/        ← 存档 Q&A
```

## 核心设计决策

| 决策 | 原因 |
|---|---|
| Daily notes 不入库 | 250+ 篇日记主要是时间块数据，已由周/月报汇总 |
| Task 文件聚合处理 | 289 个 task 不生成 289 个页面，聚合到项目 entity 页 |
| Hot.md ≤500 字 | 9600 token 上下文窗口限制，hot.md 是"工作记忆" |
| 矛盾检测保守策略 | Qwen 32B 不擅长深层语义推理，只检测数值矛盾 |
| DataviewJS 不进 wiki | wiki 页面应包含静态摘要，不依赖 Obsidian 运行时 |

## 上下文预算分配

每次 LLM 调用的 9600 token 分配：

| 用途 | Token 预算 | 说明 |
|---|---|---|
| Schema 指令 | ~2000 | 从 ingest/query/lint.md 中提取相关段落 |
| 页面模板 | ~500 | 对应类型的模板 |
| 源文档/页面 | ~4000 | 1-3 篇源文档（ingest）或 3-5 个 wiki 页（query） |
| index.md | ~1500 | 目录索引（query 时需要） |
| LLM 回答空间 | ~1600 | 留给生成回答 |

## 使用方式

### 阶段 0：设计确认（当前）
本目录下的文件是设计文档。Review 后确认或调整。

### 阶段 1：PoC 验证
1. 将 Schema 复制到 `PARA-Vault/_schema/`
2. 手动用一篇文档走一遍 ingest 流程（直接让 Qwen 按 schema 生成）
3. 手动用一个问题走一遍 query 流程
4. 验证 Qwen 32B 能否在 9600 token 限制内完成

### 阶段 2：引擎开发
在 ai-paas 中开发 Wiki 引擎（`wiki_ingest.py`、`wiki_query.py`、`wiki_lint.py`），自动化上述流程。

### 阶段 3：反哺 obsidian-nexus
Schema 稳定后，添加到 obsidian-nexus 的 `VaultPARA/_schema/` 作为社区模板。
