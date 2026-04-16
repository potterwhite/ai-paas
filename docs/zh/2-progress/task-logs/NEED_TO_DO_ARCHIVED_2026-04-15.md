
## 2026-04-15 — /download 页面 UX 修复

- [x] 下载进度一直转圈无反馈 → 修复：加入进度条（SSE百分比驱动）+ 状态文字 + 百分比计数；实时更新，用户可见每个阶段进度
- [x] AI转录应为下载字幕的子功能 → 修复：toggleTranscribe() — 字幕未勾选时转录选项 grayed out + disabled，样式缩进表示层级关系

## 2026-04-16 — YouTube 下载假完成 + 目录权限修复

- [x] **下载假完成**：`api_download` 完成后扫描目标目录，会把下载前已存在的文件也列入"下载完成"清单，导致误报。修复：下载开始前先快照现有文件名集合，完成后只列新增文件；无新文件时报错。（`services/webapp/main.py`）
- [x] **目录锁头/无写权限**：`tv/`、`movies/`、`music/`、`files/` 目录在 UI 显示🔒（不可写）。根因：NFS root-squash 把容器 root（uid=0）映射为 nobody，无法写入 `root:root drwxr-xr-x` 目录。修复：TrueNAS NFS Share 设置 `Maproot User = root`，容器内写入验证通过，API `/api/media-dirs` 确认全部 `writable: true`。
