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
