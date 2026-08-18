# HivisionIDPhotos — 手动安装沙箱

AI 证件照：上传人像 → 抠图 → 换底色 → 按标准尺寸裁切排版。

**这个容器是个空壳。** 镜像里只有 apt 层的系统库（opencv 依赖的 `libGL` 那一坨），
Python 包和应用代码一个都没有 —— 全部由你进容器手动装，装坏了删掉容器重来。

---

## 设计约定

| 东西 | 位置 | 删容器后 |
|---|---|---|
| 应用代码 | 宿主机 `data/idphoto/src` → 容器 `/workspace` | **保留** |
| 模型权重 | 同上（在 clone 目录里面） | **保留** |
| pip 缓存 | 宿主机 `data/idphoto/pip-cache` | **保留**（重装只需几十秒） |
| pip 装的包 | 容器内 | **归零** ← 这就是「重来一遍」清掉的东西 |
| apt 装的包 | 容器内 | **归零** |

**不对外发布端口。** `deploy_api.py` 在容器内监听 `8080`，`ai_webapp` 通过内部网络
`http://ai_idphoto:8080` 访问它。要手动测就进容器 curl `127.0.0.1:8080`。

---

## 一、准备目录 + 拉代码和权重到本地（宿主机上做，需要联网）

这一步做完，之后删容器重建都**不再需要网络**。

```bash
cd /home/james/ai-paas
mkdir -p data/idphoto/src data/idphoto/pip-cache

git clone https://github.com/Zeyi-Lin/HivisionIDPhotos.git data/idphoto/src
cd data/idphoto/src
mkdir -p hivision/creator/weights hivision/creator/retinaface/weights
```

### 权重下载

⚠️ **不要用官方的 `scripts/download_model.py`** —— 它有 bug：CLI 参数写的是
`birefnet-lite`，内部字典 key 却是 `birefnet-v1-lite`，传进去直接报错；
而 `retinaface-resnet50` 根本没进 CLI 选项，脚本选不到。下面用 curl 绕开。

```bash
# ① birefnet-v1-lite (224 MB) —— 画质最好，本项目默认用它
#    注意：权重在 ZhengPeng7/BiRefNet 那个 repo，文件名完全不同，必须重命名
curl -L --retry 3 -o hivision/creator/weights/birefnet-v1-lite.onnx \
  https://github.com/ZhengPeng7/BiRefNet/releases/download/v1/BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx

# ② retinaface-resnet50 —— 人脸检测，比默认的 mtcnn 准
curl -L --retry 3 -o hivision/creator/retinaface/weights/retinaface-resnet50.onnx \
  https://github.com/Zeyi-Lin/HivisionIDPhotos/releases/download/pretrained-model/retinaface-resnet50.onnx

# ③ 以下三个是备用 / 对照模型，想省时间可以先跳过
curl -L --retry 3 -o hivision/creator/weights/modnet_photographic_portrait_matting.onnx \
  https://github.com/Zeyi-Lin/HivisionIDPhotos/releases/download/pretrained-model/modnet_photographic_portrait_matting.onnx
curl -L --retry 3 -o hivision/creator/weights/hivision_modnet.onnx \
  https://github.com/Zeyi-Lin/HivisionIDPhotos/releases/download/pretrained-model/hivision_modnet.onnx
curl -L --retry 3 -o hivision/creator/weights/rmbg-1.4.onnx \
  "https://huggingface.co/briaai/RMBG-1.4/resolve/main/onnx/model.onnx?download=true"
```

下完核对一下大小（`birefnet` 应该 ~224 MB，不是几 KB 的错误页）：

```bash
ls -lh hivision/creator/weights/ hivision/creator/retinaface/weights/
```

---

## 二、起容器

```bash
cd /home/james/ai-paas
docker compose --profile idphoto up -d --build idphoto
docker exec -it ai_idphoto bash
```

---

## 三、容器内手动安装（以下都是你自己敲）

```bash
# 确认代码在（宿主机挂进来的）
ls /workspace

# 1. 装项目依赖
pip install -r requirements.txt

# 2. deploy_api.py 需要，但 requirements.txt 里没写
pip install fastapi uvicorn python-multipart

# 3. 换成 GPU 版 onnxruntime
#    requirements.txt 装的是 CPU 版 onnxruntime，和 onnxruntime-gpu
#    提供同一个 `onnxruntime` 模块，两个同时装会互相打架，必须先卸。
#    装 GPU 版之后 cpu 模式照样能跑（靠 run.sh 隐藏 CUDA 实现），
#    所以这一步装了不亏。
pip uninstall -y onnxruntime
pip install onnxruntime-gpu==1.19.2       # 1.19+ 对应 CUDA 12 + cuDNN 9，和底座镜像匹配

# 4. 起服务
run.sh
```

cpu 模式下 `run.sh` 会打一行 CUDA 初始化失败的警告，**这是预期行为**，
它会自动回退到 CPU 然后正常工作。

---

## 四、验证

`run.sh` 会占住当前终端，所以另开一个终端再进容器一次：

```bash
docker exec -it ai_idphoto bash

# 放一张测试照片到宿主机 data/idphoto/src/ 下，容器里就是 /workspace/
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

然后在宿主机 `data/idphoto/src/out.png` 打开看画质。

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

## 六、CPU / GPU 切换

改 `.env` 里的 `IDPHOTO_DEVICE`，然后重建容器（约 2 秒，什么都不会丢）：

```bash
# 改成 IDPHOTO_DEVICE=gpu
docker stop ai_vllm_qwen                          # ⚠️ 必须先停！见下
docker compose --profile idphoto up -d idphoto
docker exec -it ai_idphoto run.sh
```

⚠️ **GPU 模式必须先停 vLLM。** birefnet 的 GPU 通路要 ~16 GB 显存，
`ai_vllm_qwen` 占着 24 GB 里的 ~22 GB，装不下。

**画质上 cpu 和 gpu 完全没有区别** —— 同一个 `.onnx` 权重、同样的运算，
只是算得快慢不同。所以除非你嫌等得烦，没必要为此停掉大模型。

参考耗时（作者在 M1 Max 上实测，本机 EPYC 7551 单核更弱，估计更慢）：

| 组合 | 内存 | 耗时 |
|---|---|---|
| MODNet + mtcnn | 410 MB | 0.2 s |
| birefnet-v1-lite + retinaface | 6.2 GB | 7 s |
