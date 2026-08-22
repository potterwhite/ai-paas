# archive/

死代码存放处，暂留备查，后期删除。这里的文件没有任何调用方——不被任何脚本、
`docker-compose.yml` 或控制器引用。用 `git mv` 移入，`git log --follow` 仍可查完整历史。

目录结构对应原路径：`archive/services/comfyui/x.sh` 来自 `services/comfyui/x.sh`。

---

## 2026-08-21 移入 —— 均被 `services/comfyui/setup.sh` 覆盖

ComfyUI 真正的下载入口只有 `setup.sh`，两条触发路径：

- `./paas-controller.sh prepare` → `scripts/data_models.sh:438`
- 容器启动钩子 → `services/comfyui/user-scripts/pre-start.sh:47`

下面三个脚本调用方为零，唯一的交叉引用是 `install-nodes.sh` 里一行 echo 提到
`download-models.sh`，两者一起移走，不留悬空引用。

| 文件 | 行数 | 说明 |
|---|---|---|
| `download-models.sh` | 148 | `setup.sh` 步骤 2 的真子集：同样 11 个 URL、同样目标路径 |
| `download-liveportrait-models.sh` | 92 | `setup.sh` 步骤 3 的子集，且**从未成功运行过**——它请求 `appearance_feature.pth`，真实文件名是 `appearance_feature_extractor.pth` |
| `install-nodes.sh` | 99 | 与 `setup.sh` 步骤 1 装同样 4 个节点 |

**遗留问题**：`setup.sh` 步骤 3 也是坏的，但坏法不同——它从
`KwaiVGI/LivePortrait/.../pretrained_weights/` 取文件，该目录在仓库里不存在
（真实目录是 `liveportrait/`），5 个请求全部 404，而 `setup.sh:406` 结尾是
`|| true`，错误被吞掉后照样打印 `[done]`。这是 `setup.sh` 里的活 bug，待修。
