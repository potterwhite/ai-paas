import os
from llmcompressor import oneshot
from llmcompressor.modifiers.quantization import QuantizationModifier

# 1. 绝对不能有空格的本地路径
MODEL_DIR = "/Development/docker/docker-volumes/ai_paas/gemma-4-26B-A4B"
OUTPUT_DIR = "/Development/docker/docker-volumes/ai_paas/gemma-4-26B-A4B-W4A16"

# 2. 配置量化参数 (W4A16)
recipe = QuantizationModifier(
    targets="Linear",         # 尝试量化所有 Linear 层
    scheme="W4A16",           # 权重4-bit，激活16-bit
    ignore=["lm_head"],       # 忽略最后一层，保护输出精度
)

# 3. 运行量化
print(f"[*] 准备加载模型: {MODEL_DIR}")
print("[*] 注意：26B 模型约需要 52GB 内存加载。你的物理机 32GB RAM + 64GB Swap 会触发 Swap。")
print("[*] 看到终端卡住不要慌，这是在把模型读进 Swap 中，请耐心等待...")

oneshot(
    model=MODEL_DIR,
    dataset="ultrachat-200k",  # 下载并使用校准数据集
    recipe=recipe,
    output_dir=OUTPUT_DIR,
    max_seq_length=2048,
    num_calibration_samples=512,
)

print("[*] 🎉 量化任务彻底完成！产出物在:", OUTPUT_DIR)
