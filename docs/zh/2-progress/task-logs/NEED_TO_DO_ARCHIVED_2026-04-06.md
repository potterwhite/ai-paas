# NEED_TO_DO — Archived Session: 2026-04-06

> Archived from active NEED_TO_DO.md on 2026-04-06.
> All items below were completed during this session.

---

## 2026-04-06 — README rewrite, GPU page fix, manual control toggle

- [x] README 精简：去掉所有 Phase 路线图和进度引用，以成品视角重写中英文 README
      ✅ 已完成：README.md + docs/zh/README.md 均以"你能获得什么"为核心，去掉 Phase X 表格，
         架构图更新为当前 Router 架构，新增服务与端口总览表
      commit: `584bc24`

- [x] GPU 页面容器列表永远"加载中" + 手动控制开关
      ✅ 已完成：
         - 修复根本原因：JS 模板字符串反引号被 Python 转义为 `\``，导致浏览器 JS 语法错误，
           loadContainers() 未能定义，页面永远停在"加载中…"；改用 + 字符串拼接
         - 修复事件循环阻塞：docker exec_run() 改用 asyncio.to_thread() 包装
         - 新增"手动控制"toggle：默认只读显示容器状态，打开后显示启动/停止按钮 + VRAM 警告
         - 将 ai_comfyui 加入 GPU_MANAGED_CONTAINERS 白名单（之前遗漏）
- [x] GPU 页面再次无法刷新（confirm 换行 bug）+ 完整 Logs 模块
      ✅ 已完成：
         - 修复 ctrlContainer() 中 confirm() 弹窗 bug：Python triple-quoted 字符串里 '\n'
           输出为真实换行，在 JS 字符串字面量中非法，改为 '\\n'
         - 新增 /logs 页面（日志查看器）：
           · 容器选择器（7 个容器）
           · 行数选择：100/200/500/1000/全部
           · 时间范围筛选：5m/30m/1h/6h/24h
           · 复制按钮（clipboard API + textarea fallback）
           · 清空显示按钮
           · 行数 + 容器状态栏
           · 永久清除日志的 CLI 命令提示
         - 导航栏新增 📋 日志 入口
         - 后端 GET /api/logs/{container}?tail=200&since=1h
      commits: `4c8295d`

      ✅ 已完成：
         - GPU stats 现在优先用 ai_vllm exec，失败时自动 fallback 到 ai_whisper
           （ai_whisper restart:unless-stopped，基本常驻，GPU 信息不再因 vLLM 关闭而消失）
         - 容器启动/停止前弹出智能确认框：列出需要先停哪些容器（VRAM 冲突）、
           将启动什么、预计耗时；并自动先停冲突容器再启目标容器
      commit: `52d0090`

      ✅ 已完成：
         - 新增 /comfyui 页面（视觉生成入口）：ComfyUI 运行状态检测、跳转链接、工作流说明、使用步骤
         - 首页新增 3 张服务卡片：文生图、文生视频、数字人，均指向 /comfyui
         - 导航栏新增 🎨 生成 入口
      commit: `07bf54f`

      ✅ 已完成：
         - 二次修复：Python \'...\' 在 triple-quoted string 里输出为 '...'，在 HTML onclick 属性
           中破坏 JS 字符串；改用 data-action/data-name 属性 + addEventListener，彻底消除转义问题
         - /status 端点新增：GPU 卡名、驱动版本、核心利用率、GPU 温度、功耗/功耗上限、
           per-process GPU 显存占用、per-container CPU% 和 RAM
         - GPU 页面新增：4格统计卡（显存+核心利用率+温度）、GPU 进程卡、容器行显示 CPU+内存
      commits: `869690d`, `055af3e`

## Phase 4 补完（2026-04-06）

- [x] **API Key 持久化**：keys.py + deps.py 改用 SQLite（sqlite3）读写 api_keys 表，
       auth 中间件校验 config key + DB 中已注册 key，支持 create/list/delete
  files: `services/router/app/api/routes/keys.py`, `services/router/app/api/deps.py`,
         `services/router/app/models/base.py`
  commit: `77535fc`, `052db2f`

- [x] **Queue WebUI**：webapp 新增 /queue 页面，导航栏添加"队列"入口，
       自动刷新 + 代理 router `/api/v1/queue` API
  files: `services/webapp/main.py`
  commit: `77535fc`

- [x] **模型下载**：router `/api/v1/models/download` 不再返回空壳，
       改为 `docker exec ai_vllm huggingface-cli download` 实际下载
  (同时 webapp `/api/models/download` 此前已有完整实现)
  files: `services/router/app/api/routes/models.py`
  commit: `77535fc`

## Phase 3.4 数字人 — LivePortrait 工作流（2026-04-06）

- [x] **LivePortrait 数字人**：测试通过，端到端生成动画视频
  - 安装节点：PowerHouseMan/ComfyUI-AdvancedLivePortrait
  - 模型：节点首次运行自动从 HuggingFace 下载 ~500MB
    (face_yolov8n.pt, appearance_feature, motion_extractor, warping_module, spade_generator, stitching_retargeting_module)
  - 工作流：`services/comfyui/workflows/liveportrait_basic.json`
    · 4 个节点：LoadImage → VHS_LoadVideo → AdvancedLivePortrait → VHS_VideoCombine
    · 测试输出：512x512 H264 MP4，3秒，10fps
  - 测试命令：通过 ComfyUI API `/prompt` 提交，历史状态返回 success
  - 使用方法：停止 vLLM → docker restart ai_comfyui → 打开 http://192.168.0.19:8188
    拖入 liveportrait_basic.json → 上传人像照片和驱动视频 → Queue Prompt
    输出在 output/LivePortrait_*.mp4
  - 文件：`install-nodes.sh`, `liveportrait_basic.json`
  - commit: `2dbc995`

- [x] **comfyui demo 启动方案**：
  - 文生视频：CogVideoX-5B 工作流 `cogvideox5b_basic.json`
  - 数字人：LivePortrait 工作流 `liveportrait_basic.json`
  - 两个工作流都在 ComfyUI 中可加载执行

## 顶层目录清理（2026-04-06 已完成）

- [x] **删除废弃 LiteLLM 文件**：
  - `litellm_config.yaml` — Phase 4 后不再被引用
  - `data/litellm_data/` — 空目录
  - `data/litellm_pgdata/` — 旧 LiteLLM PostgreSQL 数据
  - `gpu-switch.sh` — Phase 4 后由 Router 自动调度替代
- [x] **更新 .gitignore / .env.example** — 清理过时路径，精简为当前需要的变量
- [x] **更新 codebase_map.md** — 中英文版同步，移除废弃文件引用
- [x] **git commit** — `54c7192`

## 手动下载模型指南（2026-04-06 已完成）

- [x] **编写模型下载指南**：`docs/zh/4-for-beginner/models_guide.md`
  - 覆盖三种下载方式：huggingface-cli（推荐）、git clone、wget 逐文件
  - 目录结构验证要求（config.json + safetensors + tokenizer）
  - vLLM 配置更新步骤 + Router 别名切换
  - 常见问题排查表（GGUF 格式、OOM、路径错误等）

## 模型下载页面迭代（2026-04-07 已完成）

- [x] **HuggingFace 搜索 + 浏览下载**：webapp `/models` 页面全面改造
      files: `services/webapp/main.py`
      - 新增后端代理端点：
        · `GET /api/hf/search?q=&limit=&sort=&type=&quant=` — 代理 HF API 搜索
        · `GET /api/hf/info/{repo_id}` — 获取单个模型详情
        · `GET /api/hf/size/{repo_id}` — 计算 .safetensors 文件总大小
      - 前端重构：
        · 搜索栏：支持关键字搜索 + "浏览全部"按钮
        · 过滤器：模型类型（LLM/文生图/文生视频/语音识别）、量化格式（AWQ/GPTQ/GGUF）、排序方式
        · 搜索结果卡片：显示模型名（含 HF 超链）、作者、类型、下载量、量化 badges、"下载到 PaaS"按钮
        · 下载进度区：从搜索结果点击下载后展示实时日志
        · 已下载模型列表：保留原有功能（列表 + 切换按钮）
        · Enter 键触发搜索
