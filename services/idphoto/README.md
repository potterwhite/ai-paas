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

### 3. 建容器

```bash
docker compose --profile idphoto up -d --build idphoto
```

容器起来后**不会**自动跑 WebUI —— `0-entrypoint.sh` 探测到 pip 包还没装,会打印提示然后 `sleep infinity` 挂着等你装。

### 4. 装依赖(容器内,只做这一次)

```bash
docker exec -it ai_idphoto bash /opt/idphoto/2-install.sh
```

结尾会自己验证 —— `onnxruntime.get_device()` 必须是 `GPU`,不是就 exit 1。

### 5. 重启,从此交给平台

```bash
docker restart ai_idphoto
```

这次 `0-entrypoint.sh` 探测到依赖齐了,直接 `exec` 到 `3-run.sh` 起 WebUI。

浏览器打开 **http://192.168.0.19:8888/idphoto**

7860 **不对外发布**。ai_webapp 在 `/idphoto/ui` 反代这个容器，所有 WebUI 统一从 8888 进 ——
详见下面「入口为什么在 8888」。

**装依赖只需要这一次。** 往后开机、Router 调度、`docker restart` 都会自动起 WebUI,不用再手工跑 `2-install.sh` 或 `3-run.sh`。

---

## GPU 归 Router 调度

⚠️ birefnet-v1-lite 要约 16GB 显存,vLLM 占 22GB,这张 24GB 的卡塞不下两个。

这个互斥**不用你自己记** —— `ai_idphoto` 已经注册进 `config/gpu-registry.json`(`exclusive: true`),Router 会在启动它之前自动把 vLLM 和 ComfyUI 停掉:

```bash
# 切给 idphoto(会停掉当前占卡的服务)
curl -X POST http://192.168.0.19:4000/v1/gpu/mode \
  -H "Authorization: Bearer sk-1234" -H "Content-Type: application/json" \
  -d '{"mode":"idphoto"}'

# 切回 LLM(会停掉 idphoto)
curl -X POST http://192.168.0.19:4000/v1/gpu/mode \
  -H "Authorization: Bearer sk-1234" -H "Content-Type: application/json" \
  -d '{"mode":"llm"}'
```

或者直接用 ai_webapp 的 `/gpu` 面板点。

compose 里那个 `profiles: ["idphoto"]` **不是** GPU 锁,它只是启动过滤器 —— 作用是让 `docker compose up -d` 只**创建**容器而不启动它,把「什么时候启动」的决定权交给 Router。真正的互斥在 `services/router/app/core/router_engine.py`。

---

## 装坏了重来

```bash
docker rm -f ai_idphoto
docker compose --profile idphoto up -d idphoto
docker exec -it ai_idphoto bash /opt/idphoto/2-install.sh
docker restart ai_idphoto
```

pip 装的东西在容器层里,删容器就没了。clone、权重、pip 缓存都在宿主机 bind mount 上,不受影响。第二次装走 pip 缓存,很快。

注意区分什么会丢容器层:

| 操作 | 依赖 |
|---|---|
| `docker restart` / Router start-stop / `paas-controller.sh stop`+`start` | ✅ 保留 |
| `docker rm` / `--build` / `--force-recreate` / `docker compose down` | ❌ 丢,要重装 |

所以平台正常关机重启**不用**重装 —— `stop_services()` 用的是 `docker compose stop` 而不是 `down`,就是为了这个。

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
| `0-entrypoint.sh` | 容器启动时 Docker 自动跑,**你不会手工调它**。探测依赖:装了就起 WebUI,没装就打印提示挂住 |
| `1-download-weights.sh` | 宿主机跑,下 2 个 onnx + 校验字节数 |
| `2-install.sh` | 容器内跑,装依赖 + 自验证。幂等。**只在安装阶段跑一次** |
| `3-run.sh` | 起 WebUI。由 `0-entrypoint.sh` 调用,一般不用手工跑 |

`services/idphoto/` 整个目录挂到容器 `/opt/idphoto:ro`。

挂**目录**不挂单文件是有原因的:单文件 bind mount 绑的是源文件 inode,你在宿主机改文件换了 inode,容器里那个挂载点还指着旧 inode,看到的是旧内容。挂目录按路径逐次解析,**改完立刻生效,不用重建容器**。

---

## WebUI 和 API 是两个东西

| | 文件 | 端口 | 有页面 |
|---|---|---|---|
| WebUI | `app.py` | 7860(仅内网) | ✅ Gradio |
| API | `deploy_api.py` | 8080(仅内网) | ❌ 7 个 POST 接口 |

`3-run.sh` 跑的是 WebUI。`deploy_api.py` 没有任何页面,浏览器打开是空的 —— 它是留给以后 ai_webapp 集成用的,走内部网络 `http://ai_idphoto:8080`。

---

## 入口为什么在 8888

这个容器**两个端口都不对外发布**。浏览器访问的是 `http://192.168.0.19:8888/idphoto`,
由 ai_webapp 反代过来:

```
浏览器 → ai_webapp:8888 /idphoto        → 落地页(容器状态 + 一键切 GPU + iframe)
       → ai_webapp:8888 /idphoto/ui/*   → 反代 → ai_idphoto:7860/*
```

跑的是**上游原版 Gradio,一行没改**,所以功能不会因为反代而缺失。

三个咬合的点,改任何一个都要一起改:

1. **`GRADIO_ROOT_PATH=/idphoto/ui`**(docker-compose.yml)— 告诉 Gradio 自己的公开子路径,
   它据此给浏览器发资源 URL。必须与 `main.py` 的 `IDPHOTO_PREFIX` 一致。
2. **代理必须转发 `x-forwarded-host`**(`services/webapp/main.py`)— Gradio 的
   `get_root_url()` 靠这个头拼公开地址;没有它会回落到请求 URL,也就是内网的
   `http://ai_idphoto:7860/...`,浏览器解析不了,页面能开但什么都加载不出来。
3. **SSE 读超时必须是 `None`** — Gradio 4.x 用 SSE(`/queue/data`、`/heartbeat`)回传进度,
   连接和标签页同寿。任何有限的 read timeout 都会把长推理掐断在中途。

Gradio 4.44 **不用 WebSocket**,所以普通流式 HTTP 代理就够了。

⚠️ 摄像头输入用不了 —— `getUserMedia` 要求 secure context,纯 HTTP 的局域网地址不满足。
这跟反代无关,直连 7860 时也一样。

⚠️ 增删 `ports:` 会强制 `--force-recreate`,而 pip 装在容器可写层 → 之后要重跑 `2-install.sh`。

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
