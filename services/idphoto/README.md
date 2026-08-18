# ai_idphoto — HivisionIDPhotos 手动安装沙盒

AI 证件照。RTX 3090 推理。

镜像是个**空壳** —— 只有 apt 系统库,没有任何 pip 包,没有应用代码。所有东西你自己进容器装。装坏了删容器重来,代码和权重不会丢。

> **铁律:`$MODELS_PATH/idphoto/src` 是上游 clone,永远不改。**
> 我们的所有修正都在 `services/idphoto/` 里。上游那份 `requirements.txt` 有缺陷,
> 我们不去改它,而是用我们自己的 `requirements.txt`。

---

## 装

### 1. clone 上游

```bash
mkdir -p /Development/docker/docker-volumes/ai_paas/idphoto/{src,pip-cache}
git clone https://github.com/Zeyi-Lin/HivisionIDPhotos.git \
  /Development/docker/docker-volumes/ai_paas/idphoto/src

# pip 缓存必须归 root：pip 只认属主 uid，不看权限位，
# 属主不是当前用户就直接禁用缓存（重装时白下 300MB+）
sudo chown -R 0:0 /Development/docker/docker-volumes/ai_paas/idphoto/pip-cache
```

### 2. 下权重(宿主机)

```bash
bash services/idphoto/1-download-weights.sh
```

214MB + 105MB,aria2c 16 线程。脚本会校验字节数 —— 必须校验,因为下载重定向失败会写一个 HTML 错误页进去,文件名和扩展名都对,直到 onnxruntime 报个看不懂的错才暴露。

### 3. 起容器

```bash
docker compose --profile idphoto up -d --build idphoto
```

### 4. 装依赖(容器内)

```bash
docker exec -it ai_idphoto bash /opt/idphoto/2-install.sh
```

结尾会自己验证 —— `onnxruntime.get_device()` 必须是 `GPU`,不是就 exit 1。

### 5. 跑

```bash
docker exec -it ai_idphoto bash /opt/idphoto/3-run.sh
```

浏览器打开 **http://192.168.0.19:7860**

⚠️ 跑之前把 `ai_vllm_*` 全停掉。birefnet-v1-lite 要约 16GB 显存,vLLM 占 22GB,这张 24GB 的卡塞不下两个。

---

## 装坏了重来

```bash
docker rm -f ai_idphoto
docker compose --profile idphoto up -d idphoto
docker exec -it ai_idphoto bash /opt/idphoto/2-install.sh
```

pip 装的东西在容器层里,删容器就没了。clone、权重、pip 缓存都在宿主机 bind mount 上,不受影响。第二次装走 pip 缓存,很快。

---

## 两个静默陷阱

装的时候一切正常、不报错,但结果是错的 —— 所以 `2-install.sh` 结尾一定要断言。

**1. `onnxruntime` 是 CPU 版**

上游 `requirements.txt` 写的是 `onnxruntime>=1.15.0`,那个 wheel 没有 CUDA provider。`hivision/creator/human_matting.py:40` 拿 `onnxruntime.get_device()`,返回 `"CPU"`,第 42 行就选了 `CPUExecutionProvider`。**不报错,只是慢十倍。** 必须换 `onnxruntime-gpu`。

**2. 版本装成 1.18 会退回 CPU**

onnxruntime-gpu ≤1.18 链 `libcudnn.so.8`,≥1.19 链 `libcudnn.so.9`。我们的镜像是 `nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04`,带的是 **cuDNN 9.5.1,没有 `.so.8`**。装 1.18 会加载不到 CUDA provider,又是静默退回 CPU。

上游 README 写 1.18.0,是因为它那行上面注明了「假如你的电脑安装的是 CUDA 12.x, **cuDNN 8**」。规则一样,cuDNN 版本不同而已。

顺带:上游提到的 `pip install torch` **不用装**。那是给「始终配置不好 cuDNN」的人的拐杖 —— torch 的 wheel 自带一套 cuDNN,拿来顶替。我们镜像里 cuDNN 是好的,省下 2.5GB。

---

## 我们的文件

| 文件 | 用途 |
|---|---|
| `Dockerfile` | 空壳镜像:CUDA 12.6.3 + cuDNN 9 + python3 + 几个 libGL |
| `requirements.txt` | 我们修正过的依赖。**不是**上游那份 |
| `1-download-weights.sh` | 宿主机跑,下 2 个 onnx + 校验字节数 |
| `2-install.sh` | 容器内跑,装依赖 + 自验证。幂等 |
| `3-run.sh` | 容器内跑,起 WebUI |

`services/idphoto/` 整个目录挂到容器 `/opt/idphoto:ro`。

挂**目录**不挂单文件是有原因的:单文件 bind mount 绑的是源文件 inode,你在宿主机改文件换了 inode,容器里那个挂载点还指着旧 inode,看到的是旧内容。挂目录按路径逐次解析,**改完立刻生效,不用重建容器**。

---

## WebUI 和 API 是两个东西

| | 文件 | 端口 | 有页面 |
|---|---|---|---|
| WebUI | `app.py` | 7860(已发布) | ✅ Gradio |
| API | `deploy_api.py` | 8080(仅内网) | ❌ 7 个 POST 接口 |

`3-run.sh` 跑的是 WebUI。`deploy_api.py` 没有任何页面,浏览器打开是空的 —— 它是留给以后 ai_webapp 集成用的,走内部网络 `http://ai_idphoto:8080`。

7860 这个端口:8080 和 8443 是 Harbor 的 nginx,8081 是 ai_rag,8888 是 ai_webapp。

---

## 模型质量

| 模型 | 大小 | 质量 |
|---|---|---|
| birefnet-v1-lite | 214MB | 最好,唯一能吃 GPU 的 |
| rmbg-1.4 | 176MB | 中 |
| MODNet | 24.7MB | 一般 |

只下了 birefnet-v1-lite。WebUI 的模型下拉框是扫 `hivision/creator/weights/*.onnx` 生成的,所以只会出现已下载的。

人脸检测:`mtcnn`(pip 装的 `mtcnn-runtime`,默认)和 `retinaface-resnet50`(已下,更准)。下拉框里还有个 `face++`,那是联网 API,**不要用**。

---

## 排查

```bash
docker exec ai_idphoto nvidia-smi -L        # 应有 GPU 0: NVIDIA GeForce RTX 3090
docker exec ai_idphoto ls /workspace        # 应有 deploy_api.py、app.py、hivision/
docker exec ai_idphoto ls /opt/idphoto      # 应有我们那几个脚本
nvidia-smi                                  # 跑之前确认显存是空的
```

`docker exec` 进去时那句 `groups: cannot find name for group ID 993` 是正常的 —— 宿主机的 video 组 gid 在容器里没有对应名字,不影响。
