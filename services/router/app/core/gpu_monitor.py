#
# Copyright (c) 2026 PotterWhite
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
"""GPU monitoring via pynvml."""

import pynvml


def init_nvml():
    """Initialize pynvml — safe to call multiple times."""
    try:
        pynvml.nvmlInit()
        return True
    except pynvml.NVMLError:
        return False


def get_gpu_info() -> list[dict]:
    """Return per-GPU metrics dict."""
    try:
        pynvml.nvmlInit()
    except pynvml.NVMLError:
        return []

    device_count = pynvml.nvmlDeviceGetCount()
    gpus = []
    for i in range(device_count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilization_rates(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        power = pynvml.nvmlDeviceGetPowerUsage(handle)  # in milliwatts

        gpus.append({
            "id": i,
            "name": pynvml.nvmlDeviceGetName(handle),
            "vram_used_mb": round(mem.used / 1024 / 1024, 1),
            "vram_free_mb": round(mem.free / 1024 / 1024, 1),
            "vram_total_mb": round(mem.total / 1024 / 1024, 1),
            "gpu_util_pct": util.gpu,
            "mem_util_pct": util.memory,
            "temperature_c": temp,
            "power_w": round(power / 1000, 1),
        })
    return gpus
