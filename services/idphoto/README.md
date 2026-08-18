# HivisionIDPhotos — 手动安装沙箱

AI 证件照：上传人像 → 抠图 → 换底色 → 按标准尺寸裁切排版。

**这个容器是个空壳。** 镜像里只有 apt 层的系统库（opencv 依赖的 `libGL` 那一坨），
Python 包和应用代码一个都没有 —— 全部由你进容器手动装，装坏了删掉容器重来。

---

## 设计约定

工作目录挂在 `MODELS_PATH` 下（`/Development`，独立的 1 TB 数据盘），
不放在仓库里 —— 权重 + pip 缓存接近 1 GB，不占 196 GB 的系统盘。

`$MODELS_PATH/idphoto` 展开后是 `/Development/docker/docker-volumes/ai_paas/idphoto`，
宿主机上有个软链接可以少敲字：`~/docker-volumes/ai_paas/idphoto`。

| 东西 | 位置 | 删容器后 |
|---|---|---|
| 应用代码 | 宿主机 `$MODELS_PATH/idphoto/src` → 容器 `/workspace` | **保留** |
| 模型权重 | 同上（在 clone 目录里面） | **保留** |
| pip 缓存 | 宿主机 `$MODELS_PATH/idphoto/pip-cache` | **保留**（重装只需几十秒） |
| pip 装的包 | 容器内 | **归零** ← 这就是「重来一遍」清掉的东西 |
| apt 装的包 | 容器内 | **归零** |

**不对外发布端口。** `deploy_api.py` 在容器内监听 `8080`，`ai_webapp` 通过内部网络
`http://ai_idphoto:8080` 访问它。要手动测就进容器 curl `127.0.0.1:8080`。

---

## 一、准备目录 + 拉代码和权重到本地（宿主机上做，需要联网）

这一步做完，之后删容器重建都**不再需要网络**。

```bash
mkdir -p ~/docker-volumes/ai_paas/idphoto/{src,pip-cache}
cd ~/docker-volumes/ai_paas/idphoto/src
git clone --depth 1 https://github.com/Zeyi-Lin/HivisionIDPhotos.git .
mkdir -p hivision/creator/weights hivision/creator/retinaface/weights
```

### 权重下载

⚠️ **不要用官方的 `scripts/download_model.py`** —— 它有 bug：CLI 参数写的是
`birefnet-lite`，内部字典 key 却是 `birefnet-v1-lite`，传进去直接报错；
而 `retinaface-resnet50` 根本没进 CLI 选项，脚本选不到。下面用 curl 绕开。

GitHub release 的 CDN（`objects.githubusercontent.com`）单连接限速严重，
实测只有 ~180 KB/s。用 `aria2c -x16` 多连接下载会快得多：

```bash
# ① birefnet-v1-lite (214 MB) —— 画质最好，本项目默认用它
#    注意：权重在 ZhengPeng7/BiRefNet 那个 repo，文件名完全不同，必须重命名
aria2c -x16 -s16 -k1M -d hivision/creator/weights -o birefnet-v1-lite.onnx \
  https://github.com/ZhengPeng7/BiRefNet/releases/download/v1/BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx

# ② retinaface-resnet50 (105 MB) —— 人脸检测，比默认的 mtcnn 准
aria2c -x16 -s16 -k1M -d hivision/creator/retinaface/weights -o retinaface-resnet50.onnx \
  https://github.com/Zeyi-Lin/HivisionIDPhotos/releases/download/pretrained-model/retinaface-resnet50.onnx

# ③ 以下三个是备用 / 对照模型，想省时间可以先跳过
aria2c -x16 -s16 -k1M -d hivision/creator/weights -o modnet_photographic_portrait_matting.onnx \
  https://github.com/Zeyi-Lin/HivisionIDPhotos/releases/download/pretrained-model/modnet_photographic_portrait_matting.onnx
aria2c -x16 -s16 -k1M -d hivision/creator/weights -o hivision_modnet.onnx \
  https://github.com/Zeyi-Lin/HivisionIDPhotos/releases/download/pretrained-model/hivision_modnet.onnx
aria2c -x16 -s16 -k1M -d hivision/creator/weights -o rmbg-1.4.onnx \
  "https://huggingface.co/briaai/RMBG-1.4/resolve/main/onnx/model.onnx?download=true"
```

下完**必须核对大小**：

```bash
ls -lh hivision/creator/weights/ hivision/creator/retinaface/weights/
```

`birefnet-v1-lite.onnx` 应为 **214M**，`retinaface-resnet50.onnx` 应为 **105M**。
只有几 KB 说明下到的是 HTML 错误页 —— 这个错不会当场暴露，
要等 onnxruntime 加载时才炸，报的错也看不出是这个原因。

---

## 二、起容器

### 先把 base image 拉下来（可选，但强烈建议）

`nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04` 约 2.5 GB。`daemon.json` 里的
`registry-mirrors` 只对 Docker Hub 生效，而且多数加速器对 `nvidia/cuda` 这类
**非 library 命名空间**代理得不好，会悄悄回落到原站。把加速器写进拉取路径更可靠：

```bash
docker pull docker.m.daocloud.io/nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04
docker tag  docker.m.daocloud.io/nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04 \
            nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04
```

改回标准名字之后 Dockerfile 一行都不用动，build 时发现本地已有，不再拉取。
daocloud 慢的话换 `docker.1ms.run`，用法相同。

### 构建 + 启动

```bash
cd /home/james/ai-paas
docker compose --profile idphoto build idphoto
docker compose --profile idphoto up -d idphoto
```

验证两件事，任一条不对就别往下走：

```bash
docker exec ai_idphoto ls /workspace      # 要能看到 deploy_api.py、hivision/
docker exec ai_idphoto nvidia-smi -L      # 要输出 GPU 0: NVIDIA GeForce RTX 3090
```

---

## 三、容器内手动安装（以下都是你自己敲）

```bash
docker exec -it ai_idphoto bash
```

pip 源已经通过 compose 的 `PIP_INDEX_URL` 指向清华镜像，不用另外配。

```bash
# 确认代码在（宿主机挂进来的）
ls /workspace

# 1. 装项目依赖
pip install -r requirements.txt

# 2. deploy_api.py 需要，但 requirements.txt 里没写
pip install fastapi uvicorn python-multipart

# 3. 换成 GPU 版 onnxruntime  ← 不做这步 GPU 就是白配的
#    requirements.txt 里写的是 CPU 专用的 onnxruntime。代码靠
#    onnxruntime.get_device() 判断设备（human_matting.py:40），装 CPU 版
#    它永远返回 "CPU" —— 不报错，只是默默用 CPU 跑，慢十倍且查不出原因。
#    两个包提供同一个 `onnxruntime` 模块，同时装会互相打架，必须先卸。
pip uninstall -y onnxruntime
pip install onnxruntime-gpu==1.19.2       # 必须 >=1.19：它对应 cuDNN 9，和底座镜像一致
                                          # 1.18 及以下是 cuDNN 8，会报找不到 libcudnn.so.8

# 4. 起服务
run.sh
```

装完确认 GPU 真的生效了：

```bash
python -c "import onnxruntime; print(onnxruntime.get_device(), onnxruntime.get_available_providers())"
```

要看到 `GPU` 和 `CUDAExecutionProvider`。输出 `CPU` 说明第 3 步没成功。

---

## 四、验证

`run.sh` 会占住当前终端，所以另开一个终端再进容器一次：

```bash
docker exec -it ai_idphoto bash

# 放一张测试照片到宿主机 $MODELS_PATH/idphoto/src/ 下，容器里就是 /workspace/
curl -s -X POST http://127.0.0.1:8080/idphoto \
  -F "input_image=@/workspace/test.jpg" \
  -F "human_matting_model=birefnet-v1-lite" \
  -F "face_detect_model=retinaface" \
  -F "height=413" -F "width=295" \
  | head -c 300
```

返回 `{"status": true, "image_base64_standard": "..."}` 就是通了。
返回 `{"status": false}` 一般是没检测到人脸，换张照片试试。

想直接看图，把 base64 存成文件（在容器里）：

```bash
curl -s -X POST http://127.0.0.1:8080/idphoto \
  -F "input_image=@/workspace/test.jpg" \
  -F "human_matting_model=birefnet-v1-lite" \
  -F "face_detect_model=retinaface" \
  | python -c "import sys,json,base64; d=json.load(sys.stdin); open('/workspace/out.png','wb').write(base64.b64decode(d['image_base64_standard']))"
```

然后在宿主机 `~/docker-volumes/ai_paas/idphoto/src/out.png` 打开看画质。

---

## 五、装坏了重来

```bash
cd /home/james/ai-paas
docker compose rm -sf idphoto
docker compose --profile idphoto up -d idphoto
docker exec -it ai_idphoto bash
```

代码、权重、pip 缓存都还在，回到第三步重新 `pip install` 即可（走缓存，几十秒）。

---

## 六、GPU / CPU 切换

`.env` 里的 `IDPHOTO_DEVICE` 控制，**默认 `gpu`**。改完重建容器（约 2 秒，什么都不会丢）：

```bash
docker stop ai_vllm_qwen                          # ⚠️ GPU 模式必须先停！见下
docker compose --profile idphoto up -d idphoto
docker exec -it ai_idphoto run.sh
```

⚠️ **GPU 模式和 vLLM 不能共存。** birefnet 的 GPU 通路要 ~16 GB 显存，
`ai_vllm_qwen` 占着 24 GB 里的 ~22 GB，装不下。跑之前先确认卡是空的：

```bash
nvidia-smi --query-gpu=memory.used --format=csv
```

切回 CPU 就把 `.env` 改成 `IDPHOTO_DEVICE=cpu`，`run.sh` 会隐藏 CUDA。
此时会打一行 CUDA 初始化失败的警告，**这是预期行为**，它会自动回退并正常工作。

**画质上 cpu 和 gpu 完全没有区别** —— 同一个 `.onnx` 权重、同样的运算，
只是算得快慢不同。所以除非你嫌等得烦，没必要为此停掉大模型。

参考耗时（作者在 M1 Max 上实测，本机 EPYC 7551 单核更弱，估计更慢）：

| 组合 | 内存 | 耗时 |
|---|---|---|
| MODNet + mtcnn | 410 MB | 0.2 s |
| birefnet-v1-lite + retinaface | 6.2 GB | 7 s |
