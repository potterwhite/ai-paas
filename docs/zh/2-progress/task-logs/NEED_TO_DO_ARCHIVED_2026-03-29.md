# NEED_TO_DO — Archived: 2026-03-28 to 2026-03-29
# All items in this file were completed and checked off.

---

03.28.2026 初始化

- [x] 完成文档体系重建（Phase 1 完成后，重建 docs/ 为 AI-First 双语文档结构）✅ 2026-03-28
- [x] 创建 CLAUDE.md 入口点文件 ✅ 2026-03-28

---

03.28.2026 Q&A 会议记录

- [x] **Q: PKB vs Agent AI — 两种方式是否需要互补？**
  ✅ 2026-03-28
  > 结论：两者互补，职责切分清楚。PKB 由你自己维护，不纳入 repo。

- [x] **Q: 我还有网关的概念吗？从 Xinference 换到 vLLM 之后。**
  ✅ 2026-03-28
  > 有，而且比 Xinference 时代更清晰。LiteLLM = 网关，vLLM = 推理引擎，职责分离干净。

- [x] **Q: 不需要每个应用分蛋糕（显存）。**
  ✅ 2026-03-28
  > gpu_memory_utilization=0.7 是 KV cache 池，所有请求共享，按需分配。

- [x] **Q: 能把内存（RAM）分给显存（VRAM）用吗？**
  ✅ 2026-03-28
  > 不值得。PCIe 带宽瓶颈（~32 GB/s vs VRAM ~936 GB/s），延迟从秒级变分钟级。

- [x] **Q: 在 docs 里看不到各阶段计划，难道要去 git history 里找吗？**
  ✅ 2026-03-28 commit `b8be598`
  > 已修复：新建 phases/phase1/2/3 plan.md，progress.md 改为纯索引。

- [x] **用户要求：所有计划分文件存放到 2-progress/phases/ 下，progress.md 做纯索引。**
  ✅ 2026-03-28 commit `b8be598`

- [x] **发现 bug：`litellm/qwen` 在 LiteLLM 1.82.1 中返回 400 错误，只有 `qwen` 有效。**
  ✅ 2026-03-28 commit `b8be598`

---

03.29.2026

- [x] 整理当前目录结构 + 开源准备（全景扫描、定位分析、.env 机制、双语 README）
  ✅ 2026-03-29 commits `89360cc`（目录整理）`523fda3`（双语 README）
  - 删除 3 个废弃 broken compose 备份 + xinference_models/（11 GB）
  - 新建 data/ 子目录，迁入 litellm_data/ + litellm_pgdata/
  - 引入 .env + .env.example，docker-compose.yml 移除硬编码密钥
  - 写双语 README（架构图、Why Not Ollama 对比表、Quick Start）
  - 项目定位：面向 AI agent 开发者的单卡私有 AI PaaS（Phase 2 完成后开源）
