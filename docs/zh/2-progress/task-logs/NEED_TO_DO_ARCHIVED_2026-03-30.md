# NEED_TO_DO — Archived Session: Mar30.2026

> Archived from active NEED_TO_DO.md on 2026-03-30.
> All items below were completed during this session.

---

## Mar30.2026 — 计划磋商 + 文档全面更新

- [x] 计划磋商 ✅ 2026-03-30 — 已讨论并写入文档：
      - 字幕双轨策略：yt-dlp 优先拉取 YouTube CC → fallback Whisper STT → LiteLLM 翻译
      - Web UI：60分界面，响应式，手机/平板/PC 竖屏支持，FastAPI + 原生 HTML/CSS/JS，无重型框架
      - 手动 GPU 控制面板：纳入 Phase 2（Step 2.6），`/gpu` 页面 + Docker SDK
      - 自动 Orchestrator：明确延迟到 Phase 3，在 Phase 2 手动面板基础上构建
      - 所有变更已写入 Phase 2/3 plan.md、architecture_vision.md、progress.md、CLAUDE.md
      commit: `098ee96`

- [x] CLAUDE.md 精简 ✅ 2026-03-30 — 裁剪至 ~50 行，移走详细内容到 guide.md，只保留强制要求
      commit: round-2

- [x] NEED_TO_DO.md 归档机制 ✅ 2026-03-30 — 归档协议写入 guide.md Section 2（每次必读），不再依赖 backlog 文件自身的提示行
      commit: round-2

- [x] ai_docs_system_template.md 更新 ✅ 2026-03-30 — 加入 UAQ 硬性规则模板 + NEED_TO_DO 归档协议说明
      commit: round-2

---

## Mar29.2026 (completed, migrated from previous session)

- [x] 确认 OpenClaw 通过 LiteLLM 的 agent 工具调用在最新配置下仍然正常工作
      ✅ 2026-03-29 — 查 DB spend logs 确认：
      - 2026-03-29 14:39 最新请求：model_group=qwen（正确），请求成功
      - 2026-03-28 15:10 有一条 `litellm/qwen` 失败记录（已知 bug）
      - **结论：OpenClaw 应用侧已使用正确的 `qwen` model string，无需修改**
