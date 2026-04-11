# 手动下载和安装模型指南

本指南教你如何通过命令行手动下载模型并安装到 ai-paas。

---

## 模型存放在哪里

- **宿主机路径：** `/home/james/ai-paas/models/`
- **容器内路径：** `/models/`（通过 docker-compose 挂载）
- **规则：** 每个模型有独立的子目录，例如 `models/qwen2.5-32b-instruct-awq/`

---

## 第一步 — 在 HuggingFace 上找到合适的模型

去 [huggingface.co/models](https://huggingface.co/models) 搜索。

**关键筛选条件：**
- 必须是 **safetensors 格式**（不要用 GGUF——那是 llama.cpp 用的）
- 必须是 **AWQ 或 GPTQ 量化版本**，适配 24GB 显存（RTX 3090）
- 必须 **vLLM 支持** —— 先查 [vLLM 支持的模型列表](https://docs.vllm.ai/en/latest/models/supported_models.html)

**搜索技巧：** 搜索时加上 "AWQ"，例如 `Qwen2.5 AWQ` 或 `Llama-3 AWQ`。

**验证兼容性：** 模型页面的 `config.json` 中 `"architectures"` 应包含 vLLM 支持的模型类型（如 `Qwen2ForCausalLM`、`LlamaForCausalLM`）。

---

## 第二步 — 通过命令行下载

### 方法 A：`huggingface-cli`（推荐）

```bash
# 如果没有安装 CLI 工具
pip install -U huggingface_hub

# 下载到 models 目录
cd ~/ai-paas/models
huggingface-cli download <repo_id> --local-dir ./<本地模型名>

# 示例：
# huggingface-cli download TheBloke/Llama-2-13B-chat-AWQ --local-dir ./llama2-13b-awq
```

### 方法 B：`git clone`

```bash
cd ~/ai-paas/models
git clone https://huggingface.co/<repo_id> <本地模型名> --branch main --depth 1
```

`--depth 1` 只克隆最新提交，节省时间和空间。

### 方法 C：用 `wget`/`curl` 直接下载

只适合文件数量少的模型。每个 `.safetensors` 分片 1-10 GB。

```bash
mkdir -p ~/ai-paas/models/my-model
cd ~/ai-paas/models/my-model

# 逐个下载（需要下载所有文件）：
wget https://huggingface.co/<user>/<model>/resolve/main/model.safetensors
wget https://huggingface.co/<user>/<model>/resolve/main/config.json
wget https://huggingface.co/<user>/<model>/resolve/main/tokenizer.json
wget https://huggingface.co/<user>/<model>/resolve/main/generation_config.json
# ... 以及其他文件：merges.txt, vocab.json, special_tokens_map.json 等
```

---

## 第三步 — 验证目录结构

下载后，模型目录至少应包含：

```
models/<模型名>/
├── config.json                        ← 必需
├── model-XXXXX-of-XXXXX.safetensors   ← 必需（一个或多个分片）
├── tokenizer.json                     ← 必需
├── tokenizer_config.json              ← 必需
├── generation_config.json             ← 常见
├── special_tokens_map.json            ← 常见
├── vocab.json / merges.txt            ← 分词器文件（取决于模型）
└── model.safetensors.index.json      ← 多分片时存在
```

**最低要求：** 至少 `config.json` + 至少一个 `.safetensors` 分片 + `tokenizer.json`/`tokenizer_config.json`。

---

## 第四步 — 更新 vLLM 加载新模型

1. 编辑 `/home/james/ai-paas/docker-compose.yml`
2. 找到 `vllm` 服务的 `command` 行
3. 将模型路径改为新的模型目录

```yaml
# 修改前：
command:
  - --model /models/qwen2.5-32b-instruct-awq

# 修改后（示例）：
command:
  - --model /models/llama2-13b-awq
```

4. 停止 vLLM，重新启动：
```bash
cd ~/ai-paas
docker compose stop vllm
docker compose up -d vllm
```

5. 验证模型加载成功：
```bash
curl -X POST "http://192.168.0.19:9997/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model":"/models/<新模型名>","messages":[{"role":"user","content":"hello"}],"max_tokens":10}'
```

---

## 第五步 —（可选）通过 Router 设为默认

如果通过 Router（端口 `4000`）调用，需要在 Router 配置中更新别名映射：

```python
# 在 services/router/app/api/routes/models.py 中
aliases = {
    "qwen": "/models/qwen2.5-32b-instruct-awq",  # 改为你的新模型路径
}
```

然后重启 Router：
```bash
docker compose restart router
```

---

## 常见问题

| 问题 | 解决方法 |
|---|---|
| GGUF 格式，vLLM 无法加载 | 搜索 safetensors 版本，或用 `autoawq` 转换 |
| 加载后 OOM（显存不足） | 模型太大——找 AWQ/GPTQ 量化版本 |
| 模型找不到 | 检查 docker-compose 中的路径是否与实际子目录名匹配 |
| vLLM 启动崩溃 | 检查 vLLM 是否支持该模型架构 |
| `config.json` 缺失 | 下载失败——用 huggingface-cli 重新下载 |
| 分词器错误 | 下载 `tokenizer.json` + `tokenizer_config.json` + 分词器相关文件 |

---

## 磁盘空间检查

```bash
# 查看可用空间
df -h ~/.

# 查看各模型大小
du -sh ~/ai-paas/models/*
```

每个模型大小参考：7B AWQ ~4 GB，13B ~9 GB，32B ~19 GB，72B ~42 GB。
