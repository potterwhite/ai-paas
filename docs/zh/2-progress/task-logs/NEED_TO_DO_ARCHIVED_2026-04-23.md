# 归档 — 2026-04-23

## 2026-04-23 — ComfyUI MuseTalk 集成 + workflow 修复 + gitignore 清理

- [x] **workflow 05 参数名修复**：`motion_images` → `driving_images`，修复 `TypeError: AdvancedLivePortrait.run() got an unexpected keyword argument 'motion_images'`

- [x] **workflow 06 开箱即用**：默认图片改为 `default_liveportrait_portrait.png`，ExpressionEditor 补全缺失输出（motion_link/save_exp），slider 默认值重置为中性

- [x] **workflow 07 新建（MuseTalk lip sync）**：新增 `07_digital_human_musetalk_lipsync.json`，MuseTalkRun 节点 + VHS_VideoCombine 输出

- [x] **ComfyUI 工作流文档**：新增 `docs/zh/4-for-beginner/comfyui_workflows_guide.md`，覆盖全部 7 个 workflow，含 ExpressionEditor 参数表、MuseTalk 原理、TTS→MuseTalk→ffmpeg 流程图

- [x] **MuseTalk Python 3.13 依赖修复（已固化到 setup.sh）**：
  - chumpy：`--no-build-isolation` 绕过 `import pip` bug
  - mmcv 2.2.0：patch setup.py `locals()['__version__']` → 显式 dict，`MMCV_WITH_OPS=0` 跳过 C++ 编译
  - xtcocotools 1.14.3：同样 patch
  - mmpose：`--no-deps` + 补 json-tricks/munkres
  - mmdet 3.1.0：`--no-deps` + patch hardcoded mmcv 版本门控
  - 详细 bug 记录与安装教程见 PKB: `plan-DEPLOY-musetalk-installation.md`

- [x] **MuseTalk 安装卡点记录**：`mmcv._ext` C++ extension 在 mmcv-lite 中缺失，运行时触发。所有 Python 层修复已完成，C++ ops 问题交由用户自行处理。PKB 已记录 5 条备选方案。

- [x] **gitignore 清理**：
  - 修复 `data/` 父目录 ignore 导致子目录白名单无效的问题，改为逐一列出需忽略的子目录
  - 新增 `data/chrome-profile/`、`data/cookies/`、`data/router_db/`、`data/router_redis/`
  - 修复 `models/` 误 ignore `services/router/app/models/`，加入白名单

- [x] **paas-controller.sh 新增 rebuild-comfyui 命令**：停止容器、清空 workdir、重新运行 prepare_comfyui，实现从头重建 ComfyUI 环境

- [x] **yt-dlp cookies 续期**（已实现，移至长期已完成）：`ai_cookie_manager` 容器已部署并验证，自动每 6 小时刷新

- [x] **CogVideoX I2V workflow 修复**（已在 2026-04-22 归档，此处清除遗留标记）
