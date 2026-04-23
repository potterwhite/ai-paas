- **归档规则在 guide.md Section 2，不在此处** — 请读 `docs/en/1-for-ai/guide.md` ← 始终保留这行
- **归档操作**：将已完成的 items 按日期归档到 `docs/zh/2-progress/task-logs/NEED_TO_DO_ARCHIVED_YYYY-MM-DD.md`。每次 append 到最后，当日完成当日归档。
- **在此文档中的 items 都是未完成的**。
- **每次开始工作前先读取此文件**，了解当前待办状态。

> PKB目录如下：
> /Development/docker/docker-volumes/syncthing-docker/ObsidianVault/PARA-Vault/2_AREA/10-Area-Artificial_Intelligence/Project_AI_Marketing_Personal
> 1. 一切工作进度以PKB为准
> 2. 每次完成单元工作，就需要同步git/pkb
---

### 长期目标

- **MCP/Skills 集成**：将 MCP server 对接到 vLLM 的 tool calling 能力（`--enable-auto-tool-choice --tool-call-parser hermes`），使 OpenClaw 能使用外部工具

---

### 待解决问题

- [ ] **MuseTalk mmcv._ext 卡点**（用户自行处理）：ComfyUI-MuseTalk 节点 import 时需要 mmcv C++ CUDA extension，mmcv-lite 不含，容器内无 nvcc 无法编译。所有 Python 层 patch 已完成并固化到 setup.sh。详见 PKB: `plan-DEPLOY-musetalk-installation.md`

- [ ] **目录选择器懒加载**：`http://192.168.0.19:8888/download` 目录选择器一次性全扫 300 条 cap 导致 tv 等目录被截断消失。需改为先显示 lv1 顶层目录，点击展开再加载子目录。

- [ ] **Whisper 替代模型**：将 [此文章](https://mp.weixin.qq.com/s/yqR1bC72Cvh1tjPD0eP6rw) 的模型集成为 Whisper 替代，前端页面支持选择使用 Whisper 或新模型。

---

### 多模型支持后续

- [ ] **Gemma 4 26B AWQ 量化**：对 `/models/gemma-4-26B-A4B/`（BF16 ~50GB）做 AWQ 4-bit 量化，输出到 `/models/gemma-4-26B-A4B-awq/`，然后创建 vllm-gemma 容器并测试切换
