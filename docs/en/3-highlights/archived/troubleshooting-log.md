> **ARCHIVED** — Xinference was permanently abandoned in Phase 1.4 (2026-03-22).
> Kept for history only. See `architecture_vision.md` for the decision rationale.

# Xinference 故障排查与修复全程记录

> 记录时间：2026-03-21
> 环境：Ubuntu VM / RTX 3090 24GB / Docker / Xinference + LiteLLM
> 目标：让 Xinference 成功启动 Qwen2.5 模型（vLLM 引擎 + AWQ 格式）

---

## 一、初始状态快照

| 项目 | 状态 |
|------|------|
| GPU | RTX 3090 24GB, Driver 580.126.09, CUDA 13.0, 显存空闲 |
| xinference-gpu 容器 | Exited(0)，手动创建，非 compose 管理 |
| ai_xinference 容器 | 不存在（compose 定义但未运行） |
| ai_litellm 容器 | Running，在 ai_paas_network 网络中 |
| 模型缓存 | 14B GGUF 符号链接全部断裂，blob 文件不存在 |

## 二、根因分析（三个叠加问题）

### 问题 1：模型文件全部丢失 — 符号链接断裂（致命）

**现象**：
```
cache/v2/qwen2_5-instruct-ggufv2-14b-q4_k_m/*.gguf
  → ../../../huggingface/models--Qwen--Qwen2.5-14B-Instruct-GGUF/blobs/xxxxx
```
所有 4 个 symlink 指向的 blob 目标文件完全不存在。`huggingface/` 目录下只有 `.locks`。

**推断**：模型下载可能因网络中断而不完整，或者容器重建时卷映射路径发生了变化，导致旧 symlink 失效。

**日志证据**（7B 模型也同样失败）：
```
gguf_init_from_file: failed to open GGUF file
  '...-00002-of-00002.gguf' (No such file or directory)
llama_model_load: error loading model: failed to load GGUF split
```

### 问题 2：引擎选择错误 — 一直用 llama.cpp 而非 vLLM

**现象**：日志中每一次启动尝试均为：
```
model_engine=llama.cpp, model_format=ggufv2
```
但架构规划要求使用 **vLLM 引擎 + AWQ 格式**，以获得高并发 PagedAttention 能力。

**影响**：llama.cpp 单线程推理，不支持 `gpu_memory_utilization` 参数精确控制显存。

### 问题 3：容器名不匹配（LiteLLM 连接断裂）

- compose 定义：`container_name: ai_xinference`
- 实际运行：`xinference-gpu`（手动 docker run 创建）
- LiteLLM 配置指向 `http://ai_xinference:9997/v1` → 永远找不到

**此问题与当前 Xinference 启动问题非强耦合，暂缓处理。**

## 三、修复执行过程

### 步骤 1：清理旧容器
```bash
docker rm xinference-gpu  # 成功
```

### 步骤 2：清理损坏的模型缓存
直接 rm 因权限不足失败（文件由容器内 root 创建）。
使用 Docker alpine 容器以 root 权限清理：
```bash
docker run --rm -v /home/james/ai-paas/xinference_models:/data alpine \
  sh -c "rm -rf /data/cache /data/huggingface /data/model /data/openmind_hub /data/virtualenv"
```
成功。清理后 xinference_models/ 仅剩 logs/ 目录。

### 步骤 3：通过 docker-compose 启动正确的 ai_xinference 容器
（进行中...）
