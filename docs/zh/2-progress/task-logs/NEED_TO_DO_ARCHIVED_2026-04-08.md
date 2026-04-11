# Archived Tasks - 2026-04-08

This file contains tasks completed on 2026-04-08.

---

## Completed Items

### Docker network 警告消除

- **问题**: `docker compose up` 时出现 "a network with name ai_paas_network exists but was not created" 警告
- **解决**: 将 `configs/docker-compose.yml` 中的网络配置改为 `external: true`，使用已存在的网络
- **相关文件**: `configs/docker-compose.yml` (lines 230-232)
- **状态**: ✅ 已完成

### 预置工作流模型一键下载

- **需求**: 在 web UI 和命令行提供一键下载预置工作流所需模型的功能
- **实现**:
  - Web UI `/models` 页面新增"预置工作流模型"区域，显示 SD 1.5、CogVideoX-5B、LivePortrait 各模型文件状态
  - 添加 `/api/comfyui/model-status` API，检查预置模型完整性
  - `paas-controller.sh` 新增 `preset-models` 命令，执行容器内 setup.sh 下载全部预置模型 (~40 GB)
- **相关文件**: `services/webapp/main.py` (COMFYUI_MODELS 定义, `/api/comfyui/model-status`, models_page 模板), `paas-controller.sh` (preset_models 函数)
- **状态**: ✅ 已完成

### HuggingFace 视频模型搜索功能修复

- **问题**: `/models` 页面 HuggingFace 搜索可能出现超时或无结果提示，用户反馈"永远加载中"
- **修复**:
  - 添加 AbortController 超时机制（15秒）
  - 改进错误处理，提供具体的失败原因（超时、网络错误、API 错误）
  - 修复 JavaScript 正则表达式转义问题
- **相关文件**: `services/webapp/main.py` (hfSearch, hfBrowse 函数)
- **状态**: ✅ 已完成

### 日志查看功能

- **需求**: 在命令行和 UI 都能查看 container 日志
- **实现**:
  - `paas-controller.sh` 新增 `logs` 命令，支持查看单个或全部容器的日志（实时跟踪或历史）
  - 交互式菜单选择容器，支持同时查看所有容器日志序列
- **相关文件**: `paas-controller.sh` (show_logs 函数, help 更新, case 分发)
- **状态**: ✅ 已完成

---

## Moved from NEED_TO_DO.md

Original items:

- Docker network 删除不干净 (已解决)
- 预置工作流模型下载指引 (已实现完整功能)
- HuggingFace 视频搜索无法使用 (已修复)
- paas-controller.sh 应该加入 log 的功能 (已完成)
