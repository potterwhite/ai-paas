# Source 页模板

> 用于：源文档的摘要（资源文档、周报、月报等）

```markdown
---
type: source
title: "{源文档标题}"
created: {YYYY-MM-DDTHH:MM:SS+08:00}
updated: {YYYY-MM-DDTHH:MM:SS+08:00}
tags: [wiki, ai-generated, source]
status: seed
sources:
  - "{源文档完整相对路径}"
related:
  - "[[相关实体或概念]]"
loa_min: 1
---

# {源文档标题}

## 摘要
{2-3 段概括文档的核心内容，不超过 300 字}

## 关键信息
- {信息点1}
- {信息点2}
- {信息点3}

## 提到的实体
- [[entity-1]]: {在本文中的角色}
- [[entity-2]]: {在本文中的角色}

## 提到的概念
- [[concept-1]]: {在本文中的解释}
- [[concept-2]]: {在本文中的应用}

## 操作步骤（如适用）
{从源文档中提取的步骤、命令、配置等}

## 时间线（如适用）
| 日期 | 事件 |
|------|------|
| YYYY-MM-DD | {事件描述} |
```
