# ai-paas — AI Agent 工作手册

> **目标读者：** AI 编程助手（Claude Code、Cursor、Windsurf、Copilot 等）
> **在动任何配置或代码之前，先读这份文件。**
> **Related:** [English version →](../../en/1-for-ai/guide.md)

---

## 1. 每次会话的阅读顺序

1. **本文件** — 了解如何在本仓库工作
2. **[`codebase_map.md`](codebase_map.md)** — 完整基础设施地图（替代目录扫描）
3. **[`../2-progress/progress.md`](../2-progress/progress.md)** — 当前阶段 + 任务状态
4. **[`../2-progress/NEED_TO_DO.md`](../2-progress/NEED_TO_DO.md)** — 当前待办事项（处理 bug/任务时必读）
5. **相关参考文档** — 仅在任务需要时读（API 规格等）

> 中文版为主权威文档。英文版（`docs/en/`）作为参考，存在冲突时以最后更新的为准。

---

## 2. 不可协商的规则

### 代码与配置
- 所有配置文件、注释、git commit 信息必须使用**英文**
- 与用户（人类）沟通使用**中文**
- **不要**自行结束会话 — 总是在完成后询问用户下一步

### 文档信任与扫描
- **将文档体系视为基础设施结构的唯一真实来源**
- **不要**做全目录扫描，除非文档中存在明确冲突
- 如果不确定某个文件是否存在，查阅 `codebase_map.md`，不要用 `find` 或 `ls -R`

### Commit 纪律
- **每个逻辑单元一个 commit** — 不要积累多个改动再一次性提交
- 严格遵守以下 commit 格式
- 永远不要提交会破坏服务的配置

### 文档维护
- 修改 `codebase_map.md` 中列出的任何文件后，在同一个 commit 中更新 `codebase_map.md`
- 某个 Phase 步骤完成后，在同一个 commit 中更新 `progress.md` 的状态

### 基础设施硬约束 — 严禁违反
- **所有服务必须以 Docker 容器方式运行**，禁止裸机部署
- **单张 RTX 3090 = 24 GB 显存** — 同一时间只能加载一个重型模型
- **vLLM 和 ComfyUI 不能同时运行** — 需要显存切换
- **不要在未更新文档的情况下修改 `gpu_memory_utilization`**

---

## 3. Commit 信息格式

```
<type>: <subject>

<body>

<footer>
```

**类型**（必填）：`feat` · `fix` · `docs` · `refactor` · `perf` · `test` · `build` · `chore`

**主题行**（必填）：英文，≤70 字符，现在时，首字母不大写
- ✅ `fix: increase gpu_memory_utilization to 0.7 for 16k context support`
- ✅ `feat: add whisper-faster service to docker-compose`
- ❌ `Updated stuff and fixed things`

**正文**（推荐）：用要点说明做了什么、为什么

**结尾**（推荐）：`Phase X.Y Step Z complete.`

---

## 4. 处理不同类型请求

### "部署一个新服务"
1. 提问确认（镜像来源、端口、显存影响）
2. 在 `docs/` 写方案 — **先不改任何配置**
3. 等待用户确认
4. 分步实施，每步一个 commit

### "服务挂了 / 有 bug"
1. 运行 `docker ps` 查看容器状态
2. 运行 `docker logs <容器名>` 获取错误信息
3. 修复；如果根因不明显，补充文档
4. 用 `fix:` 前缀提交

### "换模型或调整规模"
1. 查阅 `codebase_map.md` 确认当前显存预算
2. 确认改动不超过 24 GB 总量
3. 在同一个 commit 中更新 `docker-compose.yml` 和 `litellm_config.yaml`（或 router 配置）
4. 同一 commit 中更新 `codebase_map.md`

### "重构 / 重新组织"
1. 在 `docs/en/3-highlights/` 写重构方案
2. 等待用户确认
3. 分步执行

---

## 5. 常见错误

| ❌ 错误做法 | ✅ 正确做法 |
|---|---|
| 同时启动 vLLM 和 ComfyUI | 先停 vLLM 再启动 ComfyUI（显存独占） |
| 代码里硬写模型路径 | 用挂载路径 `/models/<model-dir>` |
| 用 `sk-1234` 主密钥给应用使用 | 通过 Router 的 `/api/v1/keys` 为每个应用发一个专属 key |
| 改完 3 个文件再一次性提交 | 每个逻辑步骤完成后立刻 commit |
| 不读 codebase_map 就开始工作 | 先读 codebase_map |
| 改了配置忘记更新 codebase_map | 总是在同一个 commit 中同步 codebase_map |
| 尝试使用 Xinference | 已永久放弃，不要重试（CUDA 子进程 bug） |
| vLLM+Whisper 共存时把 `gpu_memory_utilization` 设超过 0.7 | 最大 0.7；Whisper 需要约 4 GB 余量 |
| 应用直接调用 vLLM | Phase 4.5 之前：所有应用走 LiteLLM:4000；之后：走 ai_router:4000。vLLM:9997 仅供调试 |

---

## 6. 关键架构事实

- **API 网关（Phase 4.5 前）：** 所有应用调用 LiteLLM:4000，vLLM:9997 仅供调试；**Phase 4.5 后：** 由 ai_router:4000 替代 LiteLLM
- **模型别名 `qwen` 指向 32B AWQ 模型** — 应用使用 `"model": "qwen"`，不用完整路径
- **OpenClaw 必须使用模型字符串 `qwen`** — `litellm/qwen` 在 LiteLLM 1.82.1+ 中返回 400 错误；已于 2026-03-28 验证
- **工具调用需要 `--enable-auto-tool-choice --tool-call-parser hermes`** — 已在 compose 中设置；删掉这两个参数会导致 OpenClaw agent 循环失败
- **显存预算（32B 模式）：** vLLM @ 0.95 ≈ 22 GB，不能与 Whisper/ComfyUI 共存
- **容器通过 `ai_paas_network` 互联** — 容器间用 `container_name` 作为 hostname 通信
- **GPU Router 架构（Phase 4）：** FastAPI + Celery + Redis 独立服务，提供统一 API 入口 + GPU 调度。详见 `../2-progress/phases/phase4/plan.md`
- **三次 Xinference 失败尝试保存在 `archived/`** — 不要重复任何那些方案

---

## 7. 常用命令

```bash
# 查看容器状态
docker ps

# 查看日志
docker logs -f ai_vllm
docker logs -f ai_litellm

# GPU 显存状态
nvidia-smi

# 重启整个服务栈
cd /home/james/ai-paas && docker compose down && docker compose up -d

# 重启单个服务
docker compose restart ai_litellm

# 测试 LiteLLM 网关（Phase 4.5 前，应用侧）
curl -X POST "http://192.168.0.19:4000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"hello"}],"max_tokens":20}'
```
