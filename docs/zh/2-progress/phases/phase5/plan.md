# Phase 5 — SynapseERP 与 ai-paas 集成（Agent-First ERP）

> **Status:** Design notes only, implementation TBD
> **English version →** [English →](../../../en/2-progress/phases/phase5/plan.md)

---

## 愿景

ai-paas 和 SynapseERP 不是两个独立系统，而是**基础设施 vs 业务系统的分层关系**。

### 分层架构

```
┌──────────────────────────────────────────┐
│          SynapseERP（业务层）              │
│                                          │
│  synapse_pm        · 项目管理             │
│  synapse_attendance · 考勤分析            │
│  synapse_ai_inference · LLM 推理          │
│  synapse_ai_audio   · 语音处理            │
│  synapse_ai_visual  · 视觉生成            │
│  synapse_ai_orchestrator · GPU 任务管理   │
└──────────────────┬───────────────────────┘
                   │  API 调用（ai-paas /api/v1/*）
┌──────────────────▼───────────────────────┐
│          ai-paas（基础设施层）              │
│                                          │
│  ai_router — 统一 API 网关 + GPU 调度     │
│  vLLM / Whisper / ComfyUI — GPU 计算节点  │
│  Redis + Celery — 任务队列                │
└──────────────────────────────────────────┘
```

### ai-paas 提供什么

- GPU 计算能力（vLLM 推理、语音转录、视觉生成）
- 统一 API 入口（ai_router:4000）
- GPU 独占调度（自动启停容器、任务排队）
- API Key 管理（按应用/用户分发 scoped key）

### SynapseERP 做什么

- 面向用户的 AI 功能入口（提交任务、查看结果、关联到项目）
- Agent-First 接口（完整的 REST API + 结构化文档，AI Agent 可通过 API 完成所有操作）
- 规则引擎 + 审批流（人定义什么条件下 Agent 自动执行，什么情况需人工审批）
- 事件体系（业务事件发布/订阅，Agent 可订阅事件）

---

## 企业场景示例

| 角色 | 在 SynapseERP 中的功能 | 底层 AI 能力 |
|---|---|---|
| 美工/设计 | 提交生图/视频任务 → 排队 → 下载结果 | ai-paas ComfyUI via ai_router |
| 客服 | 录音上传 → 转录 → LLM 分析投诉意图 | Whisper + vLLM via ai_router |
| 市场 | 视频翻译 → 多语言输出 | Whisper + vLLM 翻译 |
| 产品经理 | 自然语言描述需求 → LLM 生成 PRD | vLLM via ai_router |

---

## Agent-First ERP 核心设计原则

1. **API 先于 UI** — 每个功能都有对应 REST 端点，没有前端页面也能完整使用
2. **结构化文档** — AI 不需要扫描代码就知道"有什么数据、怎么查、怎么改"（参照 ai-paas 的 `codebase_map.md`）
3. **事件驱动** — 不是人定期看报表，是系统主动推送事件给 Agent
4. **规则引擎 + 审批** — 人定义规则，Agent 执行，人审批异常
5. **语义层** — 数据模型有业务语义标签，AI 能理解

**开发顺序与传统 ERP 完全相反：**
传统：先做 UI → 再补 API
Agent-First：先做 API + 数据模型 + 事件 → UI 最后

---

## 依赖

- Phase 4（ai-paas GPU Router）必须完成
- SynapseERP 需要扩展 API 覆盖度和增加 Agent-Readable 文档
