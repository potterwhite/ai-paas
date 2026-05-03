# Entity 页模板

> 用于：项目、工具、人物、领域等实体

```markdown
---
type: entity
title: "{实体名称}"
created: {YYYY-MM-DDTHH:MM:SS+08:00}
updated: {YYYY-MM-DDTHH:MM:SS+08:00}
tags: [wiki, ai-generated, entity]
status: seed
sources:
  - "{源文档相对路径}"
related:
  - "[[相关页面]]"
loa_min: 1
---

# {实体名称}

## 概要
{一段话概括这个实体是什么、做什么、在知识库中的角色}

## 关键信息
- **状态**: {进行中/已完成/规划中}
- **所属领域**: [[area-{领域名}]]
- **创建时间**: {从源文档提取}
- **关键指标**: {如有}

## 与其他实体的关系
- [[entity-1]]: {关系描述}
- [[concept-1]]: {如何相关}

## 相关源文档
- [[source/doc-1]] — {一句话说明}
- [[source/doc-2]] — {一句话说明}

## 任务摘要（仅项目实体）
| 任务 | 状态 | 优先级 | 创建日期 |
|------|------|--------|----------|
| [[task_name_1]] | done | medium | 2025-09-11 |
| [[task_name_2]] | todo | high | 2025-10-01 |
```
