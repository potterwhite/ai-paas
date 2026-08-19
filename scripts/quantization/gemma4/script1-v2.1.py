# Copyright (c) 2026 PotterWhite
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
from transformers import AutoConfig
from llmcompressor import oneshot
from llmcompressor.modifiers.quantization import QuantizationModifier

MODEL_DIR = "/Development/docker/docker-volumes/ai_paas/gemma-4-26B-A4B"
OUTPUT_DIR = "/Development/docker/docker-volumes/ai_paas/gemma-4-26B-A4B-W4A16"

# 尝试手动解析 Config，验证 transformers 是否已认识它
try:
    print("[*] 正在测试 transformers 是否支持 gemma4 架构...")
    config = AutoConfig.from_pretrained(MODEL_DIR, trust_remote_code=True)
    print(f"[*] 成功识别架构: {config.model_type}")
except Exception as e:
    print(f"[!] 架构识别失败: {e}")
    exit(1)

recipe = QuantizationModifier(
    targets="Linear",         
    scheme="W4A16",           
    ignore=["lm_head"],       
)

print(f"[*] 准备加载模型并量化: {MODEL_DIR}")
print("[*] 将触发巨大的 Swap 内存交换，这可能需要 10-30 分钟，请保持耐心...")

oneshot(
    model=MODEL_DIR,
    dataset="ultrachat-200k",
    recipe=recipe,
    output_dir=OUTPUT_DIR,
    max_seq_length=2048,
    num_calibration_samples=512,
    # 允许加载模型文件夹内的自定义 python 代码（如果存在）
    trust_remote_code=True 
)

print("[*] 🎉 量化任务彻底完成！产出物在:", OUTPUT_DIR)
