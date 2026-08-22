# 模型下载：为什么放弃 git-lfs 改用 aria2c

> **目标读者：** 维护这个仓库的人和 AI Agent
> **对应代码：** `scripts/data_models.sh`（vLLM 模型）· `services/comfyui/setup.sh`（ComfyUI 模型）· `libs/{http,fileinfo,fetch}.sh`
> **决策日期：** 2026-08-22 · commit `a87be65`

这份文档记录的不只是"现在怎么做"，还有**为什么**——因为这个改动里有两个反直觉的判断，
如果只留下结论，下一个人（或下一个 AI）很可能会把它们改回去。

---

## 1. 事情是怎么暴露的

一次 `./paas-controller.sh prepare` 跑了 **2 小时 16 分钟**，然后告诉我 qwen 失败了：

```
[INFO] Step 2/2: transferring 18.0 GB of LFS objects...
cannot write data to temporary file ".git/lfs/incomplete/ece82d2c...":
  LFS: read tcp 192.168.0.19:55416->198.18.1.217:443: i/o timeout
Failed to fetch some objects from 'https://huggingface.co/Qwen/...'
[ERROR] LFS transfer failed for qwen.
```

第一反应很自然：**网络差，重试就是了。** 这台机器走透明代理，掉线是常态。

这个判断是错的，而且错得不明显。

---

## 2. 关键的一眼：失败的到底是什么

去磁盘上看了一下实际状态：

```
model-00001-of-00005.safetensors  3.94G  ✅
model-00002-of-00005.safetensors  3.98G  ✅
model-00003-of-00005.safetensors  3.95G  ✅
model-00004-of-00005.safetensors   135B  ❌  还是 LFS pointer
model-00005-of-00005.safetensors  3.48G  ✅
```

**5 个分片里 4 个已经完整落盘了。** 报错信息里那个 `ece82d2c...` 正是第 4 个分片的 LFS oid。

也就是说：18 GB 里已经成功传了 15 GB，只差 3.7 GB，
但 `git lfs pull` 的语义是"任何一个对象失败 → 整条命令返回非零"，
于是 `_download_vllm_model` 判定 qwen 失败，`prepare` 判定整个 Stage 1 失败。

**问题不在"今天挂了一个"，在于挂一个和挂五个对上层是同一个结果。**
明天网络同样抖动，同样会挂——而且没有任何机制让它逐步收敛。

顺手还发现一件事：这个目录占了 **32 GB**（worktree 15G + `.git/lfs/objects` 又一份 15G
+ `incomplete` 3.1G），而模型本身只有 18 GB。git-lfs 每个对象存两份，
所以之前专门写了 `_prune_lfs_cache()` 在事后回收——那是在给一个不该存在的问题打补丁。

---

## 3. 为什么 git-lfs 在这台机器上结构性地不行

ComfyUI 那一侧早就不用 git 下模型了，用的是 `libs/` 里的 aria2c 封装。
把两者摆在一起对比，差距不是"快一点慢一点"：

| | `git lfs pull` | aria2c（`libs/http.sh`） |
|---|---|---|
| 连接数 | 单流 | 每文件 16 连接，一条卡住不等于传输死了 |
| 卡死判定 | 干等 TCP timeout（分钟级） | `--lowest-speed-limit=32K --timeout=30`，秒级掐断 |
| 失败粒度 | 一个对象失败 → 整个模型失败 | 每文件独立重试 4 轮，坏一个不放弃其余 |
| 续传 | 有，但整对象单流 | 有，且按段续传（`--continue`） |
| 完整性 | 无逐文件校验 | 每文件下完 verify sha256 |
| 磁盘占用 | 两份（cache + worktree） | 一份 |

最后一栏顺带解释了为什么这次改动能**删掉** 150 行代码而不是加：
`_lfs_pending_bytes` / `_prune_lfs_cache` / `_setup_hf_credentials` / `HF_CRED_HELPER` / `_human_bytes`
全部是在伺候 git-lfs 的特性，换掉传输层之后它们没有存在意义了。

---

## 4. 第一个反直觉判断：sha256 从哪来

aria2c 方案的前提是**每个文件都要有预期的 sha256**——`libfetch_model` 拒绝在没有校验和的情况下运行
（理由见 `libs/fetch.sh` 的注释：一个传到 60% 就被接受的 safetensors，
会在几个月后变成一个无法诊断的加载错误）。

ComfyUI 那边的 sha256 是手抄进脚本的。我原本以为 vLLM 这边也得手抄，
一个模型 5 个分片，将来加模型就得一直抄——这是我差点因此放弃这个方案的原因。

**然后发现根本不用抄。** HuggingFace 的 tree API 直接给：

```bash
curl -s 'https://huggingface.co/api/models/<repo>/tree/main?recursive=true' \
  | jq -r '.[] | select(.lfs) | "\(.lfs.oid)  \(.path)"'
```

对 LFS 文件，返回的 `lfs.oid` **就是文件内容的 sha256**。

这一点没有只靠文档相信，做了两次实测：

```
gemma tokenizer.json  → cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f
qwen  shard 5         → 1af3bf12ce80cf2f85bacb57a7d2fd584712a945f481cf394f0c7b17983269e5
```

两个都和 API 给的 `lfs.oid` 逐字符吻合。另外一个旁证：git-lfs 报错时打印的
`ece82d2c...` 也正好等于 API 里 shard 4 的 `lfs.oid`。

> **一个陷阱：** 对**非 LFS** 文件（`config.json`、`tokenizer_config.json`、`merges.txt` 这些），
> API 返回的 `oid` 是 **git blob 的 sha1**，不是内容的 sha256。拿它当校验和会全部 mismatch。
> 所以这类小文件走 `libfetch_config`（不校验）——它们是 KB 级、vLLM 加载时会立刻解析失败、
> 重下一秒钟，三个理由都和权重相反。

---

## 5. 第二个反直觉判断：为什么不在运行时拉这个 API

既然一条 curl 就能拿到全部校验和，最"聪明"的写法显然是运行时拉清单、动态生成下载列表，
新增模型只需要填一个 repo 名，零维护。

**故意没这么做。** 理由是：

> 拿仓库当前的内容去校验刚从这个仓库下载的内容，等于什么都没校验。

如果 upstream 做了一次 force-push 或者悄悄换了权重，动态清单会**无声地跟随**——
校验和永远匹配，因为它就是从新内容算出来的。这恰好是 `libfetch_model` 存在的意义的反面。

所以校验和硬编码在 `_download_<name>()` 里，把字节钉死。仓库在我们脚下变了，
就应该**大声失败**，让人来判断该不该跟。代价是加模型要多贴几行——这个代价是值得付的。

---

## 6. 迁移：为什么一个字节都不用重下

改完之后有个现实问题：磁盘上已经有 git-lfs 下的 15 GB，要不要清掉重来？

**不用，而且不需要写任何迁移代码。** 因为 `libfetch_model` 的语义正好对上：
已存在的文件先 hash，匹配就 `[skip]`。所以：

- 完整的 4 个分片 → hash 匹配 → 跳过
- shard 4 那个 135 字节的 pointer → hash 不匹配 → `[stale]` 丢弃 → aria2c 重下

唯一丢掉的是 `.git/lfs/incomplete` 里那 3.1 GB——aria2c 的段式续传状态和 git-lfs 的
不兼容，救不回来。用 3.1 GB 换回 15 GB 不用重传，值。

实测结果：

```
[skip]     qwen shard 1/5   checksum matched
[skip]     qwen shard 2/5   checksum matched
[skip]     qwen shard 3/5   checksum matched
[stale]    qwen shard 4/5   checksum MISMATCH, discarding
[download] qwen shard 4/5
[done]     qwen shard 4/5   checksum matched      ← 10 MiB/s
[skip]     qwen shard 5/5   checksum matched
[skip]     gemma × 5        checksum matched      ← 零下载

downloaded 1   skipped 9   failed 0     全程 13 分钟
```

对比：同样两个模型，git-lfs 花了 **2h16m 并且失败**。这次 13 分钟里绝大部分是
hash 34 GiB 的读盘时间，真正的网络传输只有那 3.7 GiB。

---

## 7. 它治不了什么（别指望错了）

报错里那个 `198.18.1.217` 落在 **198.18.0.0/15**——这是 RFC 2544 的基准测试保留段，
现实中出现它只意味着一件事：**你走的是透明代理 / TUN 接口**。

aria2c 抗抖动强得多，但它**不能凭空造出一条路由**。如果代理彻底断了，16 个连接一样全断。

所以：**如果换了 aria2c 还在失败，去查代理，不要再来改这段代码。**
真正能提速的另一半是配 HF 镜像端点（`hf-mirror.com` 之类），这次没做——
本次改动只解决"结构性不可完成"，不解决"链路本身慢"。

---

## 8. 怎么加一个新模型

四处改动，都在 `scripts/data_models.sh`：

**① 取校验和**

```bash
curl -s 'https://huggingface.co/api/models/<repo>/tree/main?recursive=true' \
  | jq -r '.[] | if .lfs then "LFS   \(.path)  \(.lfs.oid)  \(.size)"
                 else      "PLAIN \(.path)  -  \(.size)" end'
```

**② 注册表 + 顺序**

```bash
declare -A VLLM_MODEL_REGISTRY=(
    [newmodel]="org/repo-name|local-dir-name|12.0GiB"
)
VLLM_MODEL_ORDER=(qwen gemma newmodel)
```

`local-dir-name` **必须**和 `docker-compose.yml` 里 `vllm-<name>` 服务的 `--model`
路径一致，否则容器会对着一个空目录启动。

**③ 清单函数** —— LFS 文件走 `libfetch_model`（带 sha256），非 LFS 走 `libfetch_config`：

```bash
_download_newmodel() {
    local dir="$1"
    local HF="https://huggingface.co/org/repo-name/resolve/main"

    libfetch_model "$HF/model-00001-of-00002.safetensors" \
        "$dir/model-00001-of-00002.safetensors" \
        "newmodel shard 1/2 (6.0GiB)" \
        "<sha256 来自上面 jq 输出的 lfs.oid>" || true
    # ... 其余分片

    libfetch_config "$HF/config.json" "$dir/config.json"
    # ... 其余小文件
}
```

每个 `libfetch_model` 后面的 **`|| true` 不要删** ——它是"一个分片坏掉不放弃其余分片"
的实现方式。失败没有被吞掉：`libfetch_model` 已经打印了 `[FAIL]` 并累加了
`LIBFETCH_FAILED`，`_download_all_vllm_models` 靠这个计数决定退出码。

**④ 分片清单**（给 `info` 显示用）—— `_vllm_expected_shards` 和 `_vllm_present_shards`
里补上文件名和字节数。

> **别忘了：** 改完在**同一个 commit** 里更新 `codebase_map.md`（guide.md 的硬规则）。

---

## 9. 两个容易踩的坑

**① `info` 查的是尺寸，不是校验和 —— 这是故意的**

`prepare_vllm_info` 报 `[complete — 5/5 shards]` 只比对了文件长度。
`prepare` 会 hash 每个字节，因为它**即将信任**这些文件；而 `info` 是随手看一眼的状态行，
为了打印它去 hash 34 GiB 要等好几分钟。输出里已经写明 `sizes checked, not checksums`。
后果是：一个长度正确但内容错误的文件在 `info` 里显示 complete，但下一次 `prepare` 一定抓得到。

**② 判断"传完了"绝不能看文件大小**

aria2c 带 `--file-allocation=none` 并发写 16 个段，最后一段从文件末尾附近开始写，
所以**稀疏文件的表观大小在开始几秒内就接近最终值**。
实测过：一个中断的 4.89 GB 传输，实际只到了 152 MB，`stat` 报 4.59 GB。

唯一可信的信号是 aria2c 自己的控制文件 `<dest>.aria2` 是否存在——
即 `libhttp_unfinished()`。`_vllm_present_shards` 里先调它再比尺寸，就是为了这个。

---

## 10. 现在的分工

| 谁 | 下什么 | 在哪 |
|---|---|---|
| `scripts/data_models.sh` | vLLM 权重（qwen、gemma） | 宿主机，`MODELS_PATH` 下 |
| `services/comfyui/setup.sh` | ComfyUI 全部模型（CogVideoX、SD、LivePortrait、MuseTalk…） | 容器内 |
| `services/idphoto/1-download-weights.sh` | HivisionIDPhotos 的 ONNX 权重 | 宿主机 |

三者用**同一套** `libs/{http,fileinfo,fetch}.sh`，同一套 `[skip]/[download]/[done]/[FAIL]` 输出，
同一套"校验和不匹配就重下"的语义。
唯一例外是 idphoto 那个脚本保留了 curl/wget 降级路径，因为它要能在没装 aria2c 的机器上跑。

**仓库里再没有第二种下模型的方式了。** 如果你正在写第四种，先问一下为什么。
