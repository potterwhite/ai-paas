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
