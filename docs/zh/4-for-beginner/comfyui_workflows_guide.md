# ComfyUI 内置工作流入门指南

> 适合人群：第一次打开 ComfyUI 的用户，对"工作流"概念完全陌生也没关系。
>
> 读完本文你会知道：7 个内置工作流分别做什么、背后用了什么技术、怎么开始用、以及它们如何拼成一张完整的 AI 创作地图。

---

## 什么是"工作流"

ComfyUI 是一个节点式 AI 图像/视频生成工具。你在界面里看到的一张张"连线图"就是工作流（Workflow）——每个方块是一个处理步骤，连线是数据的流动方向。

本平台在 `/workflows/` 目录下内置了 7 个开箱即用的工作流，覆盖了 AI 视觉创作的三个核心方向：

```
静态图像生成  →  视频生成  →  数字人动画
```

---

## 7 个工作流一览

| 编号 | 文件名 | 一句话 | 输入 | 输出 |
|---|---|---|---|---|
| 01 | `01_image_sd15_txt2img.json` | 用文字生成图片（经典款） | 文字提示词 | 图片 |
| 02 | `02_image_sdxl_txt2img.json` | 用文字生成图片（高清款） | 文字提示词 | 图片 |
| 03 | `03_video_cogvideox_t2v.json` | 用文字生成视频 | 文字提示词 | 视频 |
| 04 | `04_video_cogvideox_i2v.json` | 用图片生成视频 | 图片 + 文字提示词 | 视频 |
| 05 | `05_digital_human_liveportrait_drive.json` | 用视频驱动人像动起来 | 人像照片 + 驱动视频 | 视频 |
| 06 | `06_digital_human_liveportrait_expression.json` | 手动控制人像表情 | 人像照片 + 滑块 | 图片 |
| 07 | `07_digital_human_musetalk_lipsync.json` | 用语音驱动人像口型 | 人像照片 + 语音音频 | 视频 |

---

## 详细说明

### 01 — 文生图（SD 1.5）

**适合什么：** 快速出图、测试提示词、资源受限时使用。

**原理：** 使用 Stable Diffusion 1.5 模型，通过文字提示词（Prompt）引导扩散过程生成图像。

**节点流程：**
```
[CLIP Text Encode (正向提示词)]
[CLIP Text Encode (负向提示词)]  →  [KSampler]  →  [VAE Decode]  →  [SaveImage]
[Empty Latent Image (尺寸)]
```

**默认参数：** 512×512，20 步采样，CFG=7，Euler 采样器。
**显存需求：** < 4 GB。
**推荐提示词风格：** 英文，描述性词组，如 `a cat sitting on a windowsill, soft light, photorealistic`。

---

### 02 — 文生图（SDXL）

**适合什么：** 更高质量的图片，1024×1024 分辨率，人物/场景细节更丰富。

**原理：** SDXL 是 SD 1.5 的升级版，使用双 CLIP 编码器和更大的 UNet，输出质量有明显提升，但速度稍慢、显存占用更高。

**节点流程：** 与 01 类似，多了 SDXL 专用的双编码器结构。

**默认参数：** 1024×1024，25 步，CFG=7。
**显存需求：** 6–8 GB。
**与 01 的区别：** 同样的提示词在 SDXL 下细节更丰富，但需要更多显存和时间；建议先用 01 快速迭代提示词，满意后再用 02 出高清图。

---

### 03 — 文生视频（CogVideoX T2V）

**适合什么：** 用一段描述文字直接生成短视频（约 6 秒）。

**原理：** CogVideoX 是智谱 AI 的开源视频生成模型，基于扩散 Transformer 架构，直接从文本生成时序帧序列。

**节点流程：**
```
[CLIP Text Encode]  →  [CogVideoX Sampler]  →  [VAE Decode]  →  [VHS_VideoCombine]
```

**默认参数：** 480×720，49 帧（约 6 秒 @ 8fps），50 步采样。
**显存需求：** 16–20 GB（运行时会临时占满显存）。
**提示：** 描述要包含动作和场景，例如 `A red panda walks through a bamboo forest, camera slowly zooms in`。

---

### 04 — 图生视频（CogVideoX I2V）

**适合什么：** 你有一张图片，想让它"动起来"。

**原理：** 在 T2V 的基础上，将输入图像编码为条件信号，引导视频生成过程从该图像的状态出发运动。

**节点流程：**
```
[LoadImage]  →  [CogVideoX ImageEncode]  ↘
[CLIP Text Encode]                        →  [CogVideoX Sampler]  →  [VAE Decode]  →  [VHS_VideoCombine]
```

**默认输入文件：** `default_i2v_720x480.png`（已内置，直接运行可看效果）。
**显存需求：** 16–20 GB。
**技巧：** 提示词描述的动作要与图片内容相关，比如图片是一朵花，提示词写 `petals gently swaying in the breeze`。

---

### 05 — 数字人：视频驱动人像（LivePortrait Drive）

**适合什么：** 你有一张人脸照片，想用另一段视频里的面部动作来驱动它做出相同的表情和头部运动。

**原理：** 使用 LivePortrait 模型。它把"源图像"（你的人脸）和"驱动视频"（运动参考）分别编码成面部特征点和运动矢量，然后将运动迁移到源图像上，逐帧合成输出视频。整个过程不改变人物的外貌，只迁移动作。

**节点流程：**
```
[LoadImage (人像照片)]          ↘
[VHS_LoadVideo (驱动视频)]       →  [AdvancedLivePortrait]  →  [VHS_VideoCombine]
```

**默认输入文件：**
- 人像：`default_liveportrait_portrait.png`
- 驱动视频：`default_liveportrait_driving.mp4`

两个文件均已内置，**直接点 Queue 即可看到效果**，无需上传任何东西。

**关键参数（AdvancedLivePortrait 节点）：**
| 参数 | 默认值 | 说明 |
|---|---|---|
| `retargeting_eyes` | 0.0 | 眼部重定向强度，0 = 完全跟随驱动视频 |
| `retargeting_mouth` | 0.0 | 嘴部重定向强度 |
| `crop_factor` | 1.7 | 人脸裁切范围倍数，值越大保留越多背景 |

**显存需求：** < 4 GB（首次运行会下载约 350 MB 模型权重）。
**输出文件名前缀：** `LivePortrait_Drive`，保存在 ComfyUI output 目录。

---

### 06 — 数字人：表情编辑器（LivePortrait Expression）

**适合什么：** 精确控制一张人像照片的表情——让它微笑、眨眼、转头……输出单张图片，用于预览或后续制作表情序列。

**原理：** 同样基于 LivePortrait，但不使用外部驱动视频，而是通过 `ExpressionEditor` 节点手动输入各维度的数值，直接操纵面部关键点的位移量。

**节点流程：**
```
[LoadImage (人像照片)]  →  [ExpressionEditor (滑块控制)]  →  [SaveImage]
```

**默认输入文件：** `default_liveportrait_portrait.png`（直接运行可看效果）。

**完整滑块参数表（共 16 个）：**

| 索引 | 参数名 | 范围 | 默认 | 说明 |
|---|---|---|---|---|
| 0 | `rotate_pitch` | −20 ~ 20 | 0 | 头部上下点头 |
| 1 | `rotate_yaw` | −20 ~ 20 | 0 | 头部左右转动 |
| 2 | `rotate_roll` | −20 ~ 20 | 0 | 头部侧倾（歪头） |
| 3 | `blink` | −20 ~ 5 | 0 | 眨眼，负值=睁大 |
| 4 | `eyebrow` | −10 ~ 15 | 0 | 眉毛上扬/下压 |
| 5 | `wink` | 0 ~ 25 | 0 | 单眼眨眼强度 |
| 6 | `pupil_x` | −15 ~ 15 | 0 | 眼球左右方向 |
| 7 | `pupil_y` | −15 ~ 15 | 0 | 眼球上下方向 |
| 8 | `aaa` | −30 ~ 120 | 0 | 张嘴（"啊"口型） |
| 9 | `eee` | −20 ~ 15 | 0 | 龇牙（"诶"口型） |
| 10 | `woo` | −20 ~ 15 | 0 | 嘟嘴（"喔"口型） |
| 11 | `smile` | −0.3 ~ 1.3 | 0 | 微笑强度，0.3 自然，1.0 大笑 |
| 12 | `src_ratio` | 0 ~ 1 | 1.0 | 源图混合比例 |
| 13 | `sample_ratio` | −0.2 ~ 1.2 | 1.0 | 参考图混合比例 |
| 14 | `sample_parts` | 枚举 | OnlyExpression | 迁移哪些部分：仅表情/仅旋转/仅嘴/仅眼/全部 |
| 15 | `crop_factor` | 1.5 ~ 2.5 | 1.7 | 人脸裁切范围 |

**所有参数默认为 0（中性脸）**，建议第一次先只调 `smile=0.3` 看效果，逐步叠加其他参数。

**显存需求：** < 4 GB。

---

### 07 — 数字人：MuseTalk 音频口型同步

**适合什么：** 你有一段语音（TTS 生成或真人录音），想让一张人像照片张嘴"说"出这段话——嘴型与语音精确对齐，可直接用于口播、数字主播、配音场景。

**原理：** MuseTalk 使用 Whisper 提取音频特征，DWPose 检测人脸关键点，再由 UNet 生成每一帧的嘴部区域，拼合回原图得到口型同步的视频序列。全程不需要"驱动视频"，完全从音频波形推算嘴型。

**与 05 号的区别：**
| | 05 LivePortrait Drive | 07 MuseTalk |
|---|---|---|
| 驱动源 | 驱动视频（别人的面部运动） | 语音音频 |
| 嘴型 | 跟驱动视频，不对应你的台词 | 完全对应你说的话 |
| 头部/表情 | 丰富（转头、眨眼等） | 主要是嘴部 |
| 适合场景 | 表情迁移、舞蹈 | 口播、TTS 配音 |

**节点流程：**
```
[MuseTalkRun (portrait_path + audio_path)]  →  [VHS_VideoCombine]
```

**使用步骤：**
1. 准备语音文件：用任意 TTS 工具（edge-tts、OpenAI TTS 等）生成 `.wav` 文件
2. 把人像图片和语音文件上传到 ComfyUI 的 `input/` 目录
3. 在 MuseTalkRun 节点修改两个路径 widget：
   - `video_path` → `input/你的人像.png`
   - `audio_path` → `input/你的语音.wav`
4. Queue 运行，输出为带口型的 MP4 视频（**注意：无声**，需用 ffmpeg 合并音频）

**合并音频（在终端执行）：**
```bash
ffmpeg -i output/MuseTalk_LipSync_xxxxx.mp4 -i input/你的语音.wav \
  -c:v copy -c:a aac -shortest output/final_with_audio.mp4
```

**关键参数：**
| 参数 | 默认值 | 说明 |
|---|---|---|
| `video_path` | `input/default_liveportrait_portrait.png` | 人像图片路径（相对 ComfyUI 根目录）|
| `audio_path` | `input/default_musetalk_speech.wav` | 语音音频路径 |
| `bbox_shift` | 0 | 嘴部区域垂直偏移，如嘴型偏高/低可调 ±5 |
| `batch_size` | 4 | 批处理帧数，OOM 时改为 2 |

**显存需求：** < 8 GB（首次运行自动下载约 4.2 GB 模型：UNet + Whisper + SD-VAE + DWPose）。
**输出文件名前缀：** `MuseTalk_LipSync`。

---

## 完整口播流水线

07 号工作流是整条"文本→口播"流水线的核心：

```
[文字台词]
    ↓  TTS（edge-tts / OpenAI TTS）
[语音 .wav]
    ↓  07 号工作流 MuseTalk
[口型视频 .mp4（无声）]
    ↓  ffmpeg 合并音频
[最终口播视频（有声有口型）]
```

**推荐 TTS 工具（免费极快）：**
```bash
# 安装
pip install edge-tts

# 生成语音（中文女声）
edge-tts --voice zh-CN-XiaoxiaoNeural \
  --text "大家好，我是你的 AI 助手。" \
  --write-media output_speech.wav
```

---

## 为什么是这 7 个

这 7 个工作流不是随机选出来的，它们共同覆盖了当前主流 AI 视觉创作的三个维度：

```
         【维度一：输入形式】
         文字 ──→ 01 文生图 SD1.5
                ──→ 02 文生图 SDXL（质量↑）
                ──→ 03 文生视频 T2V
         图片 ──→ 04 图生视频 I2V
         照片 ──→ 05 视频驱动人像（动作迁移）
                ──→ 06 表情手动控制（精确调整）
         照片+语音 ──→ 07 音频口型同步（口播）

         【维度二：输出形式】
         静态图：01、02、06
         动态视频：03、04、05、07

         【维度三：技术架构】
         扩散模型（UNet）：01、02
         视频扩散（DiT）：03、04
         关键点迁移：05、06
         音频驱动生成：07
```

**互补关系：**
- 01 和 02 是同一技术路线的快/慢两档——先 01 迭代提示词，满意后 02 出高清。
- 03 和 04 是同一模型的两种用法——有图就用 04，没图就用 03。
- 05 和 06 是 LivePortrait 的两种控制方式——05 用视频驱动（动作迁移），06 用滑块精确控制表情。
- **07 是 05 的口播专用版**——05 迁移别人的头部运动，07 让人像张嘴说你自己的台词，各有专长。

**数字人全套流程：** 06（设计表情）→ 07（口播录制）→ 05（动作迁移/配合背景视频） → 剪辑合成。

---

## 快速上手步骤

1. 打开 ComfyUI 界面（地址见系统管理员分发的连接信息）
2. 点左上角菜单 **Load** → 选择任意一个 `.json` 文件
3. 点右侧 **Queue** 按钮运行
4. 输出文件保存在 ComfyUI 的 `output/` 目录下

> **提示：** 01、05、06 号工作流内置了默认输入文件，无需上传任何内容即可直接运行看到结果。03 号需要手动填写提示词。07 号需要先上传人像和语音文件到 `input/` 目录。

---

## 常见问题

**Q: 第一次运行 05/06 很慢？**
A: LivePortrait 模型约 350 MB，首次运行会自动下载，之后缓存到本地，后续很快。

**Q: 07 第一次运行很慢？**
A: MuseTalk 首次运行自动下载约 4.2 GB 模型（UNet + Whisper + SD-VAE + DWPose），完成后缓存在本地。

**Q: 07 号输出的视频没有声音？**
A: 这是 MuseTalk 节点的正常行为，输出只有口型视频。用 ffmpeg 合并：`ffmpeg -i 口型视频.mp4 -i 语音.wav -c:v copy -c:a aac -shortest 最终.mp4`

**Q: 03/04 运行中显卡内存不足？**
A: CogVideoX 需要 16-20 GB 显存，如果其他服务也在占用 GPU，可能冲突。先停止其他 AI 任务再试。

**Q: 我能把 06 的表情序列变成视频吗？**
A: 可以——用 06 导出多张不同表情的图片，再用视频剪辑工具拼成帧序列；或者直接换用 05 号工作流，用一段真实驱动视频一步到位。

**Q: 如何上传自己的图片？**
A: 在 ComfyUI 前端，点击 `LoadImage` 节点上的图片区域，选择本地文件上传即可。
