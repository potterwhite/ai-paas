---
title: vLLM 模型下载指南
category: operations
updated: 2026-04-08
tags: [vllm, models, download, aria2, wget]
---

# vLLM 模型下载指南

## 概述

vLLM **每次只能加载一个模型**（`--model` 参数在启动时固定）。
你可以在 `MODELS_PATH`（默认 `~/ai-paas/models/`）下存放多个模型目录，按需修改 `docker-compose.yml` 并重启 vLLM 来切换。

---

## 第一步：确认 vLLM 支持该模型

访问 [vLLM 支持模型列表](https://docs.vllm.ai/en/latest/models/supported_models.html)

常用规则：
- ✅ Qwen、LLaMA、Mistral、Gemma、DeepSeek 系列通常支持
- ✅ 量化格式：AWQ、GPTQ、fp8
- ❌ vLLM 不支持多模态视觉模型（如 LLaVA 部分版本）

---

## 第二步：找到模型文件列表

HuggingFace 模型页面 → Files and versions 标签 → 记录所有文件名。

常见 AWQ 模型文件：
```
config.json
generation_config.json
tokenizer.json
tokenizer_config.json
special_tokens_map.json
model.safetensors          # 小模型单文件
model-00001-of-00004.safetensors  # 大模型分片
model-00002-of-00004.safetensors
...
model.safetensors.index.json
```

---

## 第三步：下载模型

模型本质是一组普通文件，不需要 git 或 git-lfs，直接用 wget / aria2 下载即可。

### 方法 A：aria2（推荐，多线程，断点续传）

```bash
# 安装 aria2
sudo apt install aria2

# 创建目标目录
mkdir -p /Development/docker/docker-volumes/ai_paas/qwen2.5-7b-instruct-awq
cd /Development/docker/docker-volumes/ai_paas/qwen2.5-7b-instruct-awq

# 下载单个文件（以 Qwen2.5-7B-Instruct-AWQ 为例）
BASE="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-AWQ/resolve/main"

aria2c -x 8 -s 8 -k 1M --continue=true \
  "${BASE}/config.json" \
  "${BASE}/generation_config.json" \
  "${BASE}/tokenizer.json" \
  "${BASE}/tokenizer_config.json" \
  "${BASE}/special_tokens_map.json" \
  "${BASE}/vocab.json" \
  "${BASE}/merges.txt" \
  "${BASE}/model.safetensors.index.json" \
  "${BASE}/model-00001-of-00002.safetensors" \
  "${BASE}/model-00002-of-00002.safetensors"
```

**aria2 常用参数说明：**
- `-x 8` — 每文件最多 8 个连接
- `-s 8` — 分 8 段并行下载
- `-k 1M` — 每段最小 1MB
- `--continue=true` — 断点续传（重跑命令自动跳过已完成部分）

---

### 方法 B：wget（简单，单线程）

```bash
mkdir -p /Development/docker/docker-volumes/ai_paas/qwen2.5-7b-instruct-awq
cd /Development/docker/docker-volumes/ai_paas/qwen2.5-7b-instruct-awq

BASE="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-AWQ/resolve/main"

for FILE in \
  config.json \
  generation_config.json \
  tokenizer.json \
  tokenizer_config.json \
  special_tokens_map.json \
  vocab.json \
  merges.txt \
  model.safetensors.index.json \
  "model-00001-of-00002.safetensors" \
  "model-00002-of-00002.safetensors"; do
    wget -c "${BASE}/${FILE}"
done
```

**`-c` 参数** = 断点续传（如果文件已存在会继续下载）

---

### 方法 C：huggingface-cli（自动获取文件列表，适合不确定有哪些文件时）

```bash
pip install huggingface-hub

huggingface-cli download Qwen/Qwen2.5-7B-Instruct-AWQ \
  --local-dir /Development/docker/docker-volumes/ai_paas/qwen2.5-7b-instruct-awq \
  --local-dir-use-symlinks False
```

---

## 第四步：修改 docker-compose.yml 切换模型

编辑 `docker-compose.yml`（仓库根目录），找到 vllm service 的 `command:` 部分：

```yaml
command:
  - --model
  - /models/qwen2.5-7b-instruct-awq   # ← 改这里
  - --gpu-memory-utilization
  - "0.95"
  - --max-model-len
  - "32768"   # ← 根据新模型调整（7B AWQ 可用更大的 context）
```

**max-model-len 参考值（RTX 3090 24GB）：**

| 模型 | 量化 | 显存占用 | 建议 max-model-len |
|---|---|---|---|
| 32B AWQ | AWQ | ~22 GB | 10800（硬上限） |
| 14B AWQ | AWQ | ~9 GB | 32768 |
| 7B AWQ | AWQ | ~5 GB | 32768 |
| 7B fp16 | 无 | ~14 GB | 32768 |

---

## 第五步：重启 vLLM

```bash
# 只重启 vLLM（不影响其他容器）
docker compose up -d --force-recreate vllm

# 查看启动日志确认模型加载成功
./paas-controller.sh logs ai_vllm
```

启动成功后日志会出现：
```
INFO:     Started server process
Uvicorn running on http://0.0.0.0:8000
```

---

## 快速查看当前配置

```bash
./paas-controller.sh prepare vllm
```

---

## 注意事项

- 模型目录必须放在 `MODELS_PATH`（`.env` 中配置，默认 `~/ai-paas/models/`）下
- 容器内挂载路径是 `/models/`，所以 `--model /models/<目录名>`
- vLLM 不支持热切换，必须重启容器
- 下载时建议先用 `aria2c --dry-run` 验证 URL 是否正确
