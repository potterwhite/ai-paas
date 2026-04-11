# Phase 3 — 视觉生成 & 数字人（时分调度架构）

> 状态：✅ 完成 | 完成日期：2026-04-02
> **索引：** [← progress.md（英文）](../../../en/2-progress/progress.md) | [英文版 →](../../../en/2-progress/phases/phase3/plan.md)

---

## 目标

部署视觉 AI 服务（视频生成、数字人），**同时构建 Orchestrator（调度器），实现自动时分 GPU 调度** — 无需手动干预，自动将任务路由到合适的计算层。

**两个子目标：**
1. **内容目标** — 在 ComfyUI 中跑通视频生成和数字人的完整流程
2. **基础设施目标** — 带自动 VRAM 切换的 Orchestrator（在 Phase 2 手动 GPU 面板基础上构建）

> **与 Phase 2 的边界：**
> Phase 2 提供**手动 GPU 控制面板**（`ai_webapp` 中的 `/gpu` 页面）：用户可以查看显存占用、手动启停容器。
> Phase 3 在此基础上实现自动化：Orchestrator 监控任务队列、排空当前层、切换容器，全程无需人工干预。

---

## 为什么选时分调度（而不是静态分配显存）

静态分配（vLLM=60%，ComfyUI=40%）会同时拖慢两个工作负载：
- ComfyUI 在约 10 GB 显存下输出质量更差、速度更慢
- vLLM 低于 0.7×（约 17 GB）会破坏 OpenClaw 所需的 16k 上下文窗口

**时分调度**让每个工作负载在使用时获得它所需的 100% 资源：
- **文字/语音层**（默认常驻）：vLLM (~17 GB) + Whisper (~4 GB)
- **视觉层**（按需独占）：ComfyUI 获得完整 24 GB；文字层暂停

对于实际上很少同时需要两种任务的个人平台，这是最优的权衡方案。

---

## 架构图

```
                    ┌─────────────────────────────────────────────────────┐
                    │            ai-paas Orchestrator（调度器）           │
                    │   新服务：Web UI + VRAM 切换自动化逻辑              │
                    └──────────┬──────────────────────┬───────────────────┘
                               │ 监控状态               │ 发出调度指令
              ┌────────────────▼───┐        ┌──────────▼─────────────────┐
              │  文字/语音层       │        │  视觉层                    │
              │  （默认活跃）      │        │  （按需激活，独占 GPU）     │
              │                    │        │                            │
              │  LiteLLM :4000     │        │  ComfyUI                   │
              │  └─→ vLLM :8000    │        │  └─→ CogVideoX / SVD       │
              │  └─→ Whisper :9998 │        │  └─→ LivePortrait          │
              │                    │        │  └─→ SadTalker             │
              │  显存：~21 GB      │        │  显存：最高 24 GB          │
              └────────────────────┘        └────────────────────────────┘
```

**切换流程（由 Orchestrator 控制）：**
1. 视觉任务提交给 Orchestrator
2. Orchestrator 等待文字层排空（无飞行中的请求）
3. 停止 `ai_vllm` + `ai_whisper`
4. 启动 `ai_comfyui`
5. 执行视觉任务
6. 停止 `ai_comfyui`
7. 重启 `ai_vllm` + `ai_whisper`
8. Orchestrator 恢复路由文字请求

---

## 步骤计划

| 步骤 | 描述 | 状态 | Commit |
|---|---|---|---|
| **3.1** | 编写 Phase 3 计划；确立时分调度架构 | ✅ `b8be598` 初稿，`fa9e4e9` 修订 |
| **3.2** | 选择 ComfyUI Docker 镜像；测试 GPU 透传 + 显存读取 | ✅ `b649156` |
| **3.3** | CogVideoX-5B 工作流搭建 + 修正模型格式 | ✅ `fcd8039` |
| **3.3 附加** | 磁盘清理：删除 3 个冗余模型目录，释放 20GB | ✅ `8b5cf46` |
| **32B 升级** | vLLM 升级 Qwen2.5-32B-AWQ；gpu_memory_utilization 0.7→0.95 | ✅ `ab79c12` `202e06f` |
| **/models UI** | WebUI /models 页面上线 | ✅ `122e2df` |
| **3.4** | LivePortrait / SadTalker（数字人） | ⬜ 待执行（见 NEED_TO_DO） |
| **3.5** | 构建 Orchestrator（自动切换 + 排空） | ✅ 合并入 Phase 4.4 `8265dd3` |
| **3.6** | 扩展 `/gpu` UI 控件 | ✅ Phase 2 `/gpu` 页面已满足手动切换需求 |
| **3.7** | 暴露 ComfyUI API | ✅ 合并入 Phase 4 `8265dd3`（ComfyUI Provider + `/api/v1/tasks`） |
| **3.8** | 更新 `codebase_map.md` | ✅ `cad9916` |

---

## Orchestrator 功能规格（步骤 3.5–3.6）

**与 Phase 2 的关系：**
Phase 2 在 `ai_webapp` 中构建手动 `/gpu` 页面。Phase 3 在此基础上叠加自动化——
使用相同的 Docker SDK 集成，扩展加入任务队列处理器和排空逻辑。

**最小可用 Orchestrator：**

| 功能 | 说明 |
|---|---|
| Web UI | 显示：当前活跃层（文字/视觉）、VRAM 占用、排队中的任务 |
| 手动切换 | 按钮触发层切换（立即控制，用于紧急操作） |
| 自动切换 | 检测文字层空闲，自动启动排队的视觉任务 |
| 排空等待 | 切换前检查 LiteLLM 飞行中请求数，确保无进行中任务 |
| 自动恢复 | 视觉任务完成后，自动重启文字层 |

**实现方案：**
- 小型 Python FastAPI 服务（`ai_orchestrator` 容器）
- 使用 Docker SDK 停止/启动容器（`docker.from_env()`）
- 轮询 `nvidia-smi` 或 Docker stats 获取 VRAM 占用
- 简单任务队列（内存或 Redis）管理视觉任务请求
- Web UI：轻量 HTML+JS（无需重型框架）

---

## 显存预算

| 场景 | 活跃容器 | 显存 |
|---|---|---|
| 文字/语音层（默认） | `ai_vllm` + `ai_whisper` | ~17 + ~4 = ~21 GB |
| 视觉层（按需） | `ai_comfyui` | 最高 24 GB |
| 切换过渡中 | 均不运行 | 极少 |

⚠️ **永远不要同时运行 vLLM 和 ComfyUI。** 两者都会占用大块显存，其中一个必然 OOM。

---

## 候选模型 / 工具

| 应用场景 | 模型 | 备注 |
|---|---|---|
| 视频生成 | CogVideoX | 开源，有 ComfyUI 插件 |
| 视频生成（备选） | Stable Video Diffusion（SVD） | 显存占用更低，视频更短 |
| 数字人 | LivePortrait | 人像 + 音频 → 说话视频 |
| 数字人（备选） | SadTalker | 替代方案，也支持 ComfyUI |

---

## 执行前待确认问题

- [ ] 使用哪个 ComfyUI Docker 镜像（`ghcr.io/ai-dock/comfyui` 或其他）
- [ ] ComfyUI + CogVideoX 与 CUDA 13 的兼容性
- [ ] Orchestrator 实现方式：FastAPI vs Go vs 轻量 shell 脚本
- [ ] 排空检测：轮询 LiteLLM `/health/readiness` 还是查 DB SpendLogs？

---

## 风险

| 风险 | 缓解措施 |
|---|---|
| ComfyUI 与 CUDA 13 不兼容 | 先用最小节点图测试，再安装视频模型 |
| CogVideoX 显存需求 > 24 GB | 降级到 SVD 或使用 fp8 量化 |
| Orchestrator 排空计时不准确 | 添加宽限期 + 重试；降级到手动切换 |
| Docker SDK 权限问题（停止容器） | 先在隔离环境测试 Orchestrator 权限 |

---

## 🔍 技术调研日志（AI 执行思路记录）

> 这一节专门给人类看。记录 AI 每一步的决策依据、搜索过程、发现了什么、为什么这样选。

### Step 3.2 ComfyUI 镜像选型（2026-03-31）

**出发点：** 宿主机为 CUDA 13.0（驱动 580），需要确认哪个 ComfyUI Docker 镜像兼容，以及各模型的 VRAM 需求。

**发现 1：镜像选型**
- **ComfyUI 官方无 Docker 镜像**，两大社区镜像为：
  - `ghcr.io/ai-dock/comfyui` — 面向云平台，功能丰富
  - `yanwk/comfyui-boot` — 国人维护，更新活跃，有专用 `cu130-slim-v2` tag
- 原计划 Phase 3 写的 `ghcr.io/ai-dock/comfyui` 是 CUDA 12.x 基础；而 `yanwk/comfyui-boot:cu130-slim-v2` 直接原生 CUDA 13.0，与宿主机驱动完全匹配

**发现 2：CUDA 13.0 兼容性**
- 驱动 580 = 完全支持 CUDA 13.0
- PyTorch 2.11.0+ 已原生支持 CUDA 13.0 (`cu130` wheel)
- CUDA 12.x 容器在驱动 580 上也能运行（向后兼容），但 cu130 更干净

**发现 3：VRAM 需求验证（RTX 3090 = 24 GB）**
| 模型 | 显存峰值 | 备注 |
|---|---|---|
| CogVideoX-5B（BF16 + cpu_offload + tiling） | ~13–14 GB | 需在 ComfyUI 节点中启用优化 |
| Stable Video Diffusion（SVD，FP16 + 低分辨率） | ~10–16 GB | 需降分辨率 |
| LivePortrait（GAN 架构，非扩散模型） | < 4 GB | 极轻量 |

所有模型均在 24 GB 预算内。

**决策：**
- 选 `yanwk/comfyui-boot:cu130-slim-v2` 作为 ComfyUI 容器镜像
- 放弃原计划的 `ai-dock/comfyui`（CUDA 12.x，不如 cu130 干净）
- CogVideoX-5B 作为首选视频生成模型（社区支持最好）
- LivePortrait 作为首选数字人模型（轻量，效果好）

**当前状态：**
- [x] 调研完成，镜像选型确定
- [ ] Step 3.2：实际拉取镜像 + 测试 GPU 透传（下一步）
