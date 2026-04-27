
## 2026-04-15 — /download 页面 UX 修复

- [x] 下载进度一直转圈无反馈 → 修复：加入进度条（SSE百分比驱动）+ 状态文字 + 百分比计数；实时更新，用户可见每个阶段进度
- [x] AI转录应为下载字幕的子功能 → 修复：toggleTranscribe() — 字幕未勾选时转录选项 grayed out + disabled，样式缩进表示层级关系

## 2026-04-16 — yt-dlp cookie manager 部署验证 + 下载假完成 + 目录权限修复

- [x] **yt-dlp cookie manager 部署验证**：`docker compose --profile cookies up -d` 启动 `ai_cookie_manager`，health API 确认 healthy，cookie 文件存在，已自动刷新 2 次，无错误。`ai_webapp` 已配置 `YTDLP_COOKIES_PATH=/cookies/cookies.txt`，共享挂载正常。
- [x] **下载假完成**：`api_download` 完成后扫描目标目录，会把下载前已存在的文件也列入"下载完成"清单，导致误报。修复：下载开始前先快照现有文件名集合，完成后只列新增文件；无新文件时报错。（`services/webapp/main.py`）
- [x] **目录锁头/无写权限**：`tv/`、`movies/`、`music/`、`files/` 目录在 UI 显示🔒（不可写）。根因：NFS root-squash 把容器 root（uid=0）映射为 nobody，无法写入 `root:root drwxr-xr-x` 目录。修复：TrueNAS NFS Share 设置 `Maproot User = root`，容器内写入验证通过，API `/api/media-dirs` 确认全部 `writable: true`。

## 2026-04-22 — CogVideoX I2V workflow 修复 + paas-controller 全命令补全

- [x] **CogVideoX I2V workflow 开箱即用**：
  - 报错根因：`CogVideoX-5b-I2V` 硬性要求输入图片必须是 720×480，任何其他分辨率报 ValueError
  - 修复：新增 `ImageScale` 节点（ComfyUI 内置，无需安装）强制 resize 到 720×480，插入 LoadImage → CogVideoImageEncode 之间
  - 新增 `default_i2v_720x480.png` 默认图片，LoadImage 直接引用，点击 Run 就能出结果
  - `.gitignore` 加入 `*.png/*.jpg` 例外，确保图片 git 追踪不被 clean 删除
  - `pre-start.sh` 加入自动同步逻辑：每次容器启动将 `workflows/*.png` 复制到 `/root/ComfyUI/input/`

- [x] **paas-controller.sh 新增 start-all / stop-all / restart-all**：
  - 根因：`docker compose up -d` 不带 `--profile` 只启动无 profile 服务，`ai_comfyui` 和 `ai_cookie_manager` 不在其中
  - 修复：新增三个命令，统一带 `--profile comfyui --profile cookies`
  - 同步更新：`scripts/service.sh`、`scripts/maintenance.sh` help 文字、`paas-controller-completion.bash` Tab 补全
