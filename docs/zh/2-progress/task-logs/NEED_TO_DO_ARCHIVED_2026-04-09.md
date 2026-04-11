# Archived Tasks - 2026-04-09

This file contains tasks completed on 2026-04-09.

---

## Completed Items

### cleanall 命令

- **需求**: 给 `paas-controller.sh` 加一个 `cleanall` 命令，一次性清理所有临时文件（data/ + models/）
- **实现**: 已在 `scripts/data_models.sh` 中实现 `cleanall()` 函数，`paas-controller.sh` 的 case 分发中已注册
  - 停止所有服务
  - 清理 data/ 目录（保留 workflows 备份）
  - 清理 models/ 目录（全量删除）
  - 双重确认防止误操作
- **相关文件**: `scripts/data_models.sh` (cleanall 函数), `paas-controller.sh` (case 分发)
- **状态**: ✅ 已完成

### Auto-complete 命令行补全

- **需求**: 给 `paas-controller.sh` 加入 bash auto-complete
- **实现**: 已创建 `paas-controller-completion.bash`，支持：
  - 一级命令补全（所有主命令）
  - `logs` 子命令补全（容器名）
  - `prepare` 子命令补全（comfyui / vllm）
  - 已在 `show_help()` 中注明 source 方式
- **用法**: `source paas-controller-completion.bash` 或添加到 `~/.bashrc`
- **相关文件**: `paas-controller-completion.bash`, `scripts/maintenance.sh` (show_help 中说明)
- **状态**: ✅ 已完成

### help 菜单分组

- **需求**: 整理 `paas-controller.sh` 的命令行参数，help 菜单分组显示
- **实现**: `show_help()` 已按以下分组重组：
  - Service Management（status / start / stop / restart）
  - Logs & Monitoring（logs / disk-usage / check-deps）
  - Data & Models（clean-data / clean-models / cleanall）
  - System Maintenance（fix-permissions / reset-router / prepare / help）
- **相关文件**: `scripts/maintenance.sh` (show_help 函数)
- **状态**: ✅ 已完成

### vLLM 启动报错 OSError: config.json not found

- **问题**: vLLM 容器启动时报 `OSError: Can't load the configuration of '/models/qwen2.5-32b-instruct-awq'`
- **原因**: 这不是 bug，是正常的预期错误。模型目录不存在（未下载模型），vLLM 找不到 `config.json` 就无法启动
- **解决方案**: 下载模型到对应路径后重启即可，参考 `docs/zh/1-for-ai/vllm-model-download.md`
- **补充**: `paas-controller.sh start` 已有前置检查，会在启动前验证模型目录存在并包含 `config.json`
- **状态**: ✅ 已说明（非 bug）

### prepare comfyui — 一键下载彻底重写（用户反馈 UX 不足）

- **问题**: 修复后输出仍堆积、无换行、错误只提示路径而无操作指引，不够"一键式"
- **修复**: 完整重写 `prepare_comfyui()`：
  1. **GPU 冲突检测**：vLLM 在运行时明确说明冲突原因 + 给出具体停止命令，再询问是否强制继续
  2. **信息格式**：按 Step 分段，每段前空行，关键数字对齐（Script / Models / Total）
  3. **容器启动**：改用 `docker compose --profile comfyui up -d` 替代 `docker start`（确保 bind-mount 挂载生效）
  4. **setup.sh 兜底**：文件不存在时自动 `docker cp` 从 host 复制进容器，再设 +x 权限；host 也不存在才真正报错，并提供具体诊断命令
  5. **执行结果**：成功时输出后续步骤（UI 地址 / 如何切回 vLLM），失败时给出 retry 命令
- **相关文件**: `scripts/data_models.sh` (prepare_comfyui 函数全量重写)
- **状态**: ✅ 已修复

### prepare comfyui — 连续 bug 修复（容器冲突 + workdir placeholder + service name）

- **问题**: 每次运行 `prepare comfyui` 都有新报错，无法一键运行
- **根因链**:
  1. `docker start` 不触发 bind-mount 刷新 → 改用 `docker compose --profile comfyui up`
  2. `comfyui_workdir` 里有 Docker 自动创建的空占位文件/目录（0字节 `setup.sh`、空目录 `models` 等），遮盖了 bind-mount → 启动前自动清理
  3. fallback `docker cp` 写入 bind-mount 路径报 `device or resource busy` → 改写到 `/tmp/paas_setup.sh`
  4. `docker compose up` 的 target 写成了 container name `ai_comfyui`，应为 service name `comfyui` → 修正
  5. 旧的 exited 容器（不同 compose 项目管理）导致 name conflict → 启动前检测并 `docker rm` 旧容器
- **验证**: 完整运行流程通过：容器正常创建、`setup.sh` 正确挂载并可读取，内容正确
- **相关文件**: `scripts/data_models.sh` (prepare_comfyui Step 3 全量重写)
- **状态**: ✅ 已修复

---

## Moved from NEED_TO_DO.md

Original items:

- `[ ] paas-controller.sh 给我添加一个 cleanall` (已完成)
- `[ ] 帮我把 paas-controller.sh 的命令行能够加入 auto complete` (已完成)
- `[ ] 整理 paas-controller.sh 的命令行参数...help 菜单需要分组` (已完成)
- `[ ] 为什么 vllm 出错了？没有模型就报错？` (已说明)
- `[ ] prepare comfyui 报 setup.sh: No such file or directory` (已修复，重写)
- `[ ] 挂载被占用 chmod device or resource busy` (已修复，改用 /tmp 路径)

### stop/start/restart 命令报 ensure_env_config: command not found

- **问题**: `./paas-controller.sh stop` 报 `line 23: ensure_env_config: command not found`
- **根因**: `paas-controller.sh` 主 `main()` 里有一段调用 `ensure_env_config` 的前置 case 块，但该函数从未在任何模块中定义（遗留孤儿代码）
- **修复**: 删除 `paas-controller.sh` 中整个 `ensure_env_config` 调用块（6行），这些命令本身在各自函数里已有充分的检查逻辑
- **验证**: `./paas-controller.sh stop` 正常退出，exit code 0
- **相关文件**: `paas-controller.sh` (main 函数，删除 ensure_env_config case 块)
- **状态**: ✅ 已修复

### MODELS_PATH 设置后模型仍下载到 models/ 目录

- **问题**: `.env` 里已设 `MODELS_PATH=/Development/docker/docker-volumes/ai_paas/`，但模型仍在 `models/comfyui/` 目录
- **根因**: 旧容器（从根目录 `docker-compose.yml` 启动）挂载的是 `~/ai-paas/models/comfyui`，且 `/Development/docker/docker-volumes/ai_paas/` 目录本身不存在（`MODELS_PATH` 指向不存在的路径）
- **修复**:
  1. 创建 `MODELS_PATH` 目标目录：`mkdir -p /Development/docker/docker-volumes/ai_paas`
  2. `prepare_comfyui()` 新增 Guard A：检测 legacy 路径（`models/comfyui`）有数据而新路径为空时，提示用户选择 move / copy / skip 进行迁移
  3. 调整 Guard B（清 placeholder）顺序：移到 `docker rm` 之后执行，避免 root 权限文件 `rm` 失败
- **验证**: 完整流程通过（迁移提示显示正确，31G 数据检测正确，容器正常启动，setup.sh 找到）
- **相关文件**: `scripts/data_models.sh` (prepare_comfyui Step 3 Guard A + Guard B 顺序调整)
- **状态**: ✅ 已修复

### prepare comfyui — custom_nodes: No such file or directory（旧容器 stale mount）

- **问题**: 运行 `prepare comfyui` 报 `/root/ComfyUI/custom_nodes: No such file or directory`
- **根因**: 容器已在运行（上次测试遗留），但其 bind-mount 来自旧 compose 配置（`comfyui_workdir` 覆盖了整个 `/root/ComfyUI`，导致 `custom_nodes` 不存在），Step 3 因"容器运行中"跳过了重建逻辑，直接跑了 setup.sh
- **修复**: Step 3 前置检查：容器运行中但 `setup.sh` 不可访问 → 自动 `docker stop + docker rm` 再走重建流程
- **验证**: 脚本自动检测到 stale 容器，停止、删除，重建容器，setup.sh 正确挂载
- **相关文件**: `scripts/data_models.sh` (prepare_comfyui Step 3 新增运行时 stale 检测)
- **状态**: ✅ 已修复

### MODELS_PATH 根因彻底修复 — docker-compose.yml 位置问题

- **问题**: `MODELS_PATH=/Development/docker/docker-volumes/ai_paas` 在 `.env` 中已正确设置，但 Docker Compose 始终使用 fallback `~/ai-paas/models`。此问题已被"修复"5-10 次，每次都失败
- **根因（首次确诊）**: Docker Compose 从 `docker-compose.yml` 所在目录寻找 `.env`。compose 文件在 `configs/` 子目录，而 `.env` 在仓库根目录 → Compose 永远读不到 `.env`，所有 `${MODELS_PATH:-fallback}` 都走了 fallback。Shell 脚本通过 `source .env` 能正常工作，掩盖了 compose 级别的失败
- **修复**:
  1. `git mv configs/docker-compose.yml docker-compose.yml` — compose 文件移到根目录，Compose 自动发现 `.env`
  2. 所有 `${MODELS_PATH:-~/ai-paas/models}` fallback 改为 `${MODELS_PATH:-./models}`（4 处）
  3. `../services/...` build context 改为 `./services/...`（3 处）
- **验证**: `docker compose config | grep source.*Development` 输出 3 行正确路径 ✅
- **相关文件**: `docker-compose.yml`（从 configs/ 移至根目录）, `docs/zh/3-highlights/models_path_root_cause.md`
- **状态**: ✅ 已修复

### docker-compose.yml 硬编码路径清理

- **问题**: `docker-compose.yml` 中 11 处 `~/ai-paas/...` 硬编码路径，不可移植
- **修复**:
  - 5 处 `~/ai-paas/data/...` → `./data/...`
  - 2 处 `~/ai-paas/services/...` → `./services/...`
  - 4 处 `${MODELS_PATH:-~/ai-paas/models}` → `${MODELS_PATH:-./models}`
  - 1 处注释中的 `~/ai-paas/models/comfyui/...` → `${MODELS_PATH}/comfyui/...`
  - `download-models.sh` 中 `/home/james/ai-paas/models/comfyui` 改为动态读取 `.env` 中的 `MODELS_PATH`
- **验证**: `grep "~/" docker-compose.yml` 和 `grep "/home/james" docker-compose.yml` 均无输出 ✅
- **相关文件**: `docker-compose.yml`, `services/comfyui/download-models.sh`, `.env.example`, `scripts/data_models.sh`, `docs/zh/1-for-ai/vllm-model-download.md`
- **状态**: ✅ 已修复

### PKB 重构 — Project_AI_Marketing_Personal 主题驱动架构

- **需求**: 按照 `pkb-setup-guide-dup.md` 将 `Project_AI_Marketing_Personal` 从平面日期驱动结构重构为主题驱动的 PKB 架构
- **实现**:
  1. **主题域分离**: `deploy/`（基础设施域，9 文件）+ `strategy/`（商业/内容域，2 文件）+ `tasks/`（任务追踪，4 文件）
  2. **文件前缀系统**: `plan-` / `log-` / `bug-` / `ref-` 全部 11 文件严格遵守
  3. **Dashboard 入口**: `_DASHBOARD.md` 包含当前阶段、进度表、域地图、命名规则快查、目录导航
  4. **Roadmap Hub 模式**: 每个域有独立 roadmap 文件作为导航索引，含进度表 + 阅读顺序 + 依赖文档
  5. **YAML Frontmatter**: 所有文件均有 tags / created date / modified date / status / author
  6. **Wiki-link 交叉引用**: 全部使用 `[[filename]]` 语法，无孤立文件
- **合规性**: 12/12 项全部通过 ✅（入口点、主题结构、前缀、frontmatter、导航索引、进度表、wiki-link、无孤立文件、当前位置追踪、域地图、目录快查、阅读顺序）
- **相关文件**: `PARA-Vault/2_AREA/10-Area-Artificial_Intelligence/Project_AI_Marketing_Personal/` 目录
- **状态**: ✅ 已完成

### WebUI 模型页面修复 — JS 语法错误 + 依赖检查 + 缺失 UI 元素

- **问题**: 模型管理页面 `http://192.168.0.19:8888/models` 搜索不工作，显示"系统依赖异常"，预置工作流卡在"加载中…"
- **根因**:
  1. Python triple-quoted string 中 `\n` 被解释为真换行 → JS 单引号字符串跨行 → SyntaxError → 整个 script 块失效 → hfSearch 等函数未定义
  2. quickDownload onclick 的引号转义被 Python 消耗（`\'` → `'`）→ JS 语法错误
  3. `_check_dependencies_sync()` 硬编码 `/home/james/ai-paas`（容器内不存在）→ 永远报错
  4. `loadPresetStatus()` 在 Script Block 1 中尝试 wrap `loadModels()`，但 `loadModels` 在 Script Block 2 中定义 → wrapper 从未执行
  5. `model-list` div 缺失 → `loadModels()` 的 `getElementById` 返回 null
- **修复**:
  - `\n` → `\\n`（Python 输出字面量 `\n` 给 JS）
  - 引号正确双重转义 `\\\\'`
  - 依赖检查改用环境变量而非读 `.env` 文件；跳过 data 目录检查
  - 移除 dead wrapper 代码，在 init 区直接调用 `loadPresetStatus()`
  - 添加 `model-list` div 和 `/favicon.ico` 路由
- **相关文件**: `services/webapp/main.py`
- **状态**: ✅ 已修复

### 预置工作流模型一键下载（LivePortrait）

- **需求**: 模型页面"下载全部模型"按钮只弹 alert，不实际下载
- **实现**:
  1. `COMFYUI_MODELS` 字典添加 `download_url` 字段（LivePortrait 5 个模型从 `KlingTeam/LivePortrait` HuggingFace 仓库下载）
  2. 新增 `POST /api/comfyui/download-preset` — 接受 workflow_key，找出缺失模型，启动后台线程下载
  3. 新增 `GET /api/comfyui/download-progress/{task_id}` — 轮询下载进度
  4. 前端 `downloadPreset()` 重写为实际 API 调用 + 内联进度显示（1.5s 轮询）
- **验证**: LivePortrait 5 个模型全部下载成功（总计 499MB，5/5 files，0 errors）
- **相关文件**: `services/webapp/main.py`
- **状态**: ✅ 已完成

### 日志时区修复 — UTC → 本地时间

- **问题**: WebUI 日志页显示 Docker UTC 时间戳（如 `2026-04-09T14:38:13.900263386Z`），与本地时间不一致
- **根因**: Docker 返回 UTC 时间戳，webapp 直接透传给前端
- **修复**: 在 `_get_logs()` 中用正则匹配 ISO 时间戳，转换为本地时间（Asia/Hong_Kong UTC+8），输出格式 `YYYY-MM-DD HH:MM:SS`
- **相关文件**: `services/webapp/main.py`（`api_logs` 函数）
- **状态**: ✅ 已修复
