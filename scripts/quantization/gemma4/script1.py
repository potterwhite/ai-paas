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

from llmcompressor import oneshot
from llmcompressor.modifiers.quantization import GPTQModifier, QuantizationModifier

# AWQ 等价实现（W4A16）
recipe = QuantizationModifier(
    targets="Linear",
    scheme="W4A16",           # Weight 4-bit, Activation 16-bit (= W4A16 = AWQ 风格)
    ignore=["lm_head"],       # 最后一层不量化（保护精度）
)

oneshot(
    model="/Development/docker/docker-volumes/ai_paas/gemma-4-26B-A4B/",
    dataset="ultrachat-200k",  # 内置校准集选项
    recipe=recipe,
    output_dir=" /Development/docker/docker-volumes/ai_paas/gemma-4-26B-A4B/output",
    max_seq_length=2048,
    num_calibration_samples=512,
)
