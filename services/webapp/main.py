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
"""
ai-paas Web App — Phase 2
Routes: / (home), /subtitle, /translate, /gpu, /models, /status (JSON API)
"""

import os
import json
import subprocess
import tempfile
import asyncio
import threading
import uuid
import time
from pathlib import Path
from typing import Optional

import httpx
import docker
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles

# ── Config from environment ──────────────────────────────────────────────────
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://ai_litellm:4000/v1")
LITELLM_API_KEY  = os.getenv("LITELLM_API_KEY",  "sk-1234")
WHISPER_BASE_URL = os.getenv("WHISPER_BASE_URL",  "http://ai_whisper:8000/v1")
LLM_MODEL        = os.getenv("LLM_MODEL",         "qwen")
WHISPER_MODEL    = os.getenv("WHISPER_MODEL",      "Systran/faster-whisper-large-v3")

# ── yt-dlp cookie support ────────────────────────────────────────────────────
YTDLP_COOKIES_PATH = os.getenv("YTDLP_COOKIES_PATH", "")


def _ytdlp_base_cmd() -> list[str]:
    """Return yt-dlp base command with optional cookie authentication.

    If YTDLP_COOKIES_PATH is set and the file exists, appends --cookies.
    Otherwise returns plain ["yt-dlp"] for backward compatibility.
    """
    cmd = ["yt-dlp"]
    if YTDLP_COOKIES_PATH and Path(YTDLP_COOKIES_PATH).is_file():
        cmd.extend(["--cookies", YTDLP_COOKIES_PATH])
    return cmd

# ── Branding ────────────────────────────────────────────────────────────────
APP_NAME         = os.getenv("APP_NAME", "ai-paas")                # displayed in header + title

# ── Media storage (NFS / local) ─────────────────────────────────────────────
MEDIA_ROOT       = os.getenv("MEDIA_ROOT", "")                     # /media inside container (mapped from host)

# ── Model manager config (low-coupling: change these two vars to reuse in other projects) ──
MODELS_ROOT      = os.getenv("MODELS_ROOT", "/models")          # host path mapped into container
VLLM_CONTAINER   = os.getenv("VLLM_CONTAINER", "ai_vllm_qwen")  # default container; switching delegates to Router
HF_TOKEN         = os.getenv("HF_TOKEN", "")                    # optional; set for gated models

# ── ComfyUI model storage config ──
COMFYUI_MODELS_HDD = os.getenv("COMFYUI_MODELS_HDD", "")        # host path for large models (HDD)
COMFYUI_WORKFLOWS_DIR = os.getenv("COMFYUI_WORKFLOWS_DIR", "/comfyui_workflows")  # built-in workflow JSONs

# Containers the GPU panel is allowed to start/stop (whitelist — safety)
GPU_MANAGED_CONTAINERS = ["ai_vllm_qwen", "ai_vllm_gemma", "ai_whisper", "ai_comfyui"]

# ── In-memory download task registry ─────────────────────────────────────────
# { task_id: {"status": ..., "log": [...], "repo_id": str, "local_dir": str, "progress": {...}} }
_download_tasks: dict = {}


def _fmt_bytes(n: int) -> str:
    """Format bytes to human-readable string."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024**3:.2f} GB"


def _fmt_eta(seconds: float) -> str:
    """Format seconds to human-readable ETA."""
    if seconds < 0 or seconds > 86400 * 7:
        return "unknown"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"


class _ProgressTracker:
    """Custom tqdm-compatible class for snapshot_download's thread_map.

    snapshot_download passes tqdm_class to thread_map, which creates a progress bar
    iterating over files. This tracks file-level completion (not byte-level).
    Byte-level progress is tracked separately via directory size monitoring.
    """

    def __init__(self, *args, **kwargs):
        self.total = kwargs.get("total", 0)
        self.desc = kwargs.get("desc", "")
        self.n = 0
        self._task = kwargs.pop("_task", None)  # injected via factory
        # Set total_files from thread_map's total if available
        if self._task and self.total and self.total > 0:
            self._task["progress"]["total_files"] = self.total

    def update(self, n=1):
        self.n += n
        if self._task:
            prog = self._task["progress"]
            prog["completed_files"] = self.n
            prog["last_update"] = time.time()
            prog["stall_warning"] = False

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __iter__(self):
        return self

    def __next__(self):
        raise StopIteration

    @property
    def disable(self):
        return False

    def set_description(self, desc, refresh=True):
        self.desc = desc

    def refresh(self):
        pass


def _monitor_download_dir(task_id: str, local_dir: str, poll_interval: float = 3.0):
    """Background thread: monitor download directory size for byte-level progress.

    Calculates download speed, current file being written, and ETA.
    """
    task = _download_tasks.get(task_id)
    if not task:
        return
    prog = task["progress"]
    prev_size = 0
    prev_time = time.monotonic()

    while task["status"] == "running":
        time.sleep(poll_interval)
        if task["status"] != "running":
            break

        try:
            # Calculate total directory size
            dir_path = Path(local_dir)
            if not dir_path.exists():
                continue
            current_size = sum(f.stat().st_size for f in dir_path.rglob("*") if f.is_file())

            now = time.monotonic()
            dt = now - prev_time
            if dt > 0:
                speed = (current_size - prev_size) / dt
            else:
                speed = 0

            prog["downloaded_bytes"] = current_size

            # Find the most recently modified file (likely being downloaded)
            latest_file = None
            latest_mtime = 0
            for f in dir_path.rglob("*"):
                if f.is_file():
                    mt = f.stat().st_mtime
                    if mt > latest_mtime:
                        latest_mtime = mt
                        latest_file = f

            total_bytes = prog.get("total_bytes", 0)
            remaining = total_bytes - current_size if total_bytes > 0 else 0
            eta = remaining / speed if speed > 0 and remaining > 0 else -1

            prog["current_file"] = {
                "name": latest_file.name if latest_file else "—",
                "size": latest_file.stat().st_size if latest_file else 0,
                "downloaded": current_size,
                "speed_bps": max(0, int(speed)),
                "eta_seconds": round(eta, 1) if eta >= 0 else -1,
            }
            prog["last_update"] = time.time()

            # Stall detection: no size change for 120+ seconds
            if current_size > prev_size:
                prog["stall_warning"] = False
            # (stall_checker daemon handles the actual warning)

            prev_size = current_size
            prev_time = now

        except Exception:
            pass  # directory may not exist yet or be in transition

app = FastAPI(title=f"{APP_NAME} WebUI")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


# ── No-cache middleware for HTML pages (fix stale JS issues) ──
from starlette.middleware.base import BaseHTTPMiddleware

@app.middleware("http")
async def add_cache_control(request, call_next):
    response = await call_next(request)
    if request.url.path in ("/", "/subtitle", "/translate", "/comfyui", "/gpu", "/models", "/queue", "/logs"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# ── HTML shell ───────────────────────────────────────────────────────────────
def page(title: str, active: str, body: str) -> HTMLResponse:
    nav_links = [
        ("/",          "🏠", "首页"),
        ("/subtitle",  "🎬", "字幕"),
        ("/download",  "📥", "下载"),
        ("/translate", "🌐", "翻译"),
        ("/comfyui",   "🎨", "生成"),
        ("/gpu",       "⚡", "GPU"),
        ("/models",    "📦", "模型"),
        ("/queue",     "📋", "队列"),
        ("/logs",      "📝", "日志"),
    ]
    nav_html = "".join(
        f'<a href="{href}" class="{"active" if active == href else ""}">{icon} {label}</a>'
        for href, icon, label in nav_links
    )
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title} — {APP_NAME}</title>
  <link rel="stylesheet" href="/static/style.css">
  <style>
  /* ── Switching overlay (orb effect) ─────────────────────────────────── */
  #sw-overlay {{
    display: none;
    position: fixed; inset: 0; z-index: 9999;
    background: rgba(5,10,20,0.82);
    backdrop-filter: blur(6px);
    align-items: center; justify-content: center;
    flex-direction: column; gap: 28px;
  }}
  #sw-overlay.active {{ display: flex; }}

  /* Orb container */
  .sw-orb {{
    position: relative; width: 140px; height: 140px;
  }}
  /* Spinning ring of light shards */
  .sw-orb-ring {{
    position: absolute; inset: 0;
    animation: sw-spin 1.6s linear infinite;
  }}
  .sw-orb-ring:nth-child(2) {{ animation-duration: 2.4s; animation-direction: reverse; }}
  .sw-orb-ring:nth-child(3) {{ animation-duration: 3.2s; }}
  @keyframes sw-spin {{ to {{ transform: rotate(360deg); }} }}

  /* Individual light shards */
  .sw-shard {{
    position: absolute; border-radius: 50%;
    width: 18px; height: 18px;
    filter: blur(3px);
  }}
  /* Ring 1 — 6 cyan shards */
  .sw-orb-ring:nth-child(1) .sw-shard:nth-child(1)  {{ top:0;   left:50%; transform:translateX(-50%); background:#22d3ee; opacity:.9; }}
  .sw-orb-ring:nth-child(1) .sw-shard:nth-child(2)  {{ top:18%; right:4%; background:#38bdf8; opacity:.7; }}
  .sw-orb-ring:nth-child(1) .sw-shard:nth-child(3)  {{ bottom:18%; right:4%; background:#818cf8; opacity:.6; }}
  .sw-orb-ring:nth-child(1) .sw-shard:nth-child(4)  {{ bottom:0; left:50%; transform:translateX(-50%); background:#34d399; opacity:.8; }}
  .sw-orb-ring:nth-child(1) .sw-shard:nth-child(5)  {{ bottom:18%; left:4%; background:#a78bfa; opacity:.7; }}
  .sw-orb-ring:nth-child(1) .sw-shard:nth-child(6)  {{ top:18%; left:4%; background:#60a5fa; opacity:.6; }}
  /* Ring 2 — 4 smaller gold shards */
  .sw-orb-ring:nth-child(2) .sw-shard {{ width:12px; height:12px; background:#fbbf24; opacity:.75; filter:blur(2px); }}
  .sw-orb-ring:nth-child(2) .sw-shard:nth-child(1)  {{ top:8%;  left:50%; transform:translateX(-50%); }}
  .sw-orb-ring:nth-child(2) .sw-shard:nth-child(2)  {{ top:50%; right:8%; transform:translateY(-50%); }}
  .sw-orb-ring:nth-child(2) .sw-shard:nth-child(3)  {{ bottom:8%; left:50%; transform:translateX(-50%); background:#f472b6; }}
  .sw-orb-ring:nth-child(2) .sw-shard:nth-child(4)  {{ top:50%; left:8%;  transform:translateY(-50%); background:#4ade80; }}
  /* Ring 3 — 3 tiny white sparks */
  .sw-orb-ring:nth-child(3) .sw-shard {{ width:8px; height:8px; background:#fff; opacity:.5; filter:blur(1.5px); }}
  .sw-orb-ring:nth-child(3) .sw-shard:nth-child(1)  {{ top:4%;  left:50%; transform:translateX(-50%); }}
  .sw-orb-ring:nth-child(3) .sw-shard:nth-child(2)  {{ bottom:15%; right:15%; }}
  .sw-orb-ring:nth-child(3) .sw-shard:nth-child(3)  {{ bottom:15%; left:15%; }}
  /* Pulsing core */
  .sw-orb-core {{
    position: absolute; inset: 30px;
    border-radius: 50%;
    background: radial-gradient(circle, #38bdf8 0%, #1d4ed8 50%, transparent 100%);
    animation: sw-pulse 2s ease-in-out infinite;
    box-shadow: 0 0 30px #38bdf8, 0 0 60px #1d4ed888;
  }}
  @keyframes sw-pulse {{
    0%, 100% {{ transform: scale(1);   opacity: .85; }}
    50%       {{ transform: scale(1.12); opacity: 1; }}
  }}

  /* Text block */
  .sw-info {{ text-align: center; color: #e2e8f0; }}
  .sw-info .sw-title {{ font-size: 20px; font-weight: 700; margin-bottom: 6px; letter-spacing: .02em; }}
  .sw-info .sw-detail {{ font-size: 13px; color: #94a3b8; margin-bottom: 10px; max-width: 340px; }}
  .sw-info .sw-timer {{
    font-family: monospace; font-size: 28px; font-weight: 700;
    color: #38bdf8; text-shadow: 0 0 12px #38bdf888;
    margin-bottom: 16px;
  }}
  /* Action links */
  .sw-actions {{ display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }}
  .sw-actions a, .sw-actions button {{
    padding: 7px 18px; border-radius: 8px; font-size: 13px; font-weight: 600;
    text-decoration: none; cursor: pointer; border: none;
    transition: opacity .15s;
  }}
  .sw-actions a:hover, .sw-actions button:hover {{ opacity: .8; }}
  .sw-actions .sw-btn-gpu   {{ background: #1e3a5f; color: #7dd3fc; }}
  .sw-actions .sw-btn-home  {{ background: #14432a; color: #86efac; }}
  .sw-actions .sw-btn-hide  {{ background: #334155; color: #cbd5e1; }}
  /* Progress bar at bottom of overlay */
  .sw-progress-wrap {{
    position: fixed; bottom: 0; left: 0; right: 0; height: 4px;
    background: rgba(255,255,255,0.08);
  }}
  .sw-progress-fill {{
    height: 100%; background: #38bdf8;
    width: 0%; transition: width 1s linear;
    box-shadow: 0 0 8px #38bdf8;
  }}
  </style>
</head>
<body>
<header>
  <h1><a href="/" style="text-decoration:none;color:inherit">{APP_NAME}</a></h1>
  <nav>{nav_html}</nav>
</header>

<!-- ── Global switching overlay ─────────────────────────────────────────── -->
<div id="sw-overlay">
  <div class="sw-orb">
    <div class="sw-orb-ring">
      <div class="sw-shard"></div><div class="sw-shard"></div><div class="sw-shard"></div>
      <div class="sw-shard"></div><div class="sw-shard"></div><div class="sw-shard"></div>
    </div>
    <div class="sw-orb-ring">
      <div class="sw-shard"></div><div class="sw-shard"></div>
      <div class="sw-shard"></div><div class="sw-shard"></div>
    </div>
    <div class="sw-orb-ring">
      <div class="sw-shard"></div><div class="sw-shard"></div><div class="sw-shard"></div>
    </div>
    <div class="sw-orb-core"></div>
  </div>
  <div class="sw-info">
    <div class="sw-title" id="sw-title">正在切换...</div>
    <div class="sw-detail" id="sw-detail"></div>
    <div class="sw-timer" id="sw-timer"></div>
    <div class="sw-actions">
      <a href="/gpu"  class="sw-btn-gpu">⚡ GPU 页面</a>
      <a href="/"     class="sw-btn-home">🏠 首页</a>
      <button onclick="dismissSwitchOverlay()" class="sw-btn-hide">✕ 在后台运行</button>
    </div>
  </div>
  <div class="sw-progress-wrap"><div class="sw-progress-fill" id="sw-progress-bar"></div></div>
</div>

<main>
<div id="cookie-alert" style="display:none;"></div>
{body}</main>
<script>
var APP_NAME = '{APP_NAME}';
// ── Global switching overlay ────────────────────────────────────────────────
var _swState = null; // null = idle; object = switching in progress

function showSwitchBanner(opts) {{
  // opts: {{ title, detail, estimateSec, stopContainers, startContainer }}
  _swState = {{
    title: opts.title || '正在切换...',
    detail: opts.detail || '',
    estimateSec: opts.estimateSec || 60,
    elapsed: 0,
    pollInterval: null,
    timerInterval: null,
    startContainer: opts.startContainer || null,
    stopContainers: opts.stopContainers || [],
  }};

  document.getElementById('sw-title').textContent = _swState.title;
  document.getElementById('sw-detail').textContent = _swState.detail;
  document.getElementById('sw-timer').textContent = _fmt_countdown(_swState.estimateSec);
  document.getElementById('sw-progress-bar').style.width = '0%';
  document.getElementById('sw-overlay').classList.add('active');

  // Countdown timer
  _swState.timerInterval = setInterval(function() {{
    if (!_swState) return;
    _swState.elapsed++;
    var remain = Math.max(0, _swState.estimateSec - _swState.elapsed);
    document.getElementById('sw-timer').textContent = _fmt_countdown(remain);
    var pct = Math.min(95, (_swState.elapsed / _swState.estimateSec) * 100);
    document.getElementById('sw-progress-bar').style.width = pct + '%';
  }}, 1000);

  // Poll /api/gpu-status-lite every 4 s to detect completion
  _swState.pollInterval = setInterval(function() {{
    _pollSwitchStatus();
  }}, 4000);
}}

function _fmt_countdown(sec) {{
  if (sec <= 0) return '就绪中…';
  if (sec < 60) return sec + 's';
  return Math.floor(sec/60) + 'm ' + (sec%60) + 's';
}}

function _pollSwitchStatus() {{
  if (!_swState) return;
  fetch('/api/gpu-status-lite').then(function(r) {{ return r.json(); }}).then(function(d) {{
    var containers = d.containers || [];
    var startName = _swState.startContainer;
    if (startName) {{
      var found = containers.find(function(c) {{ return c.name === startName && c.status === 'running'; }});
      if (found) {{ _completeSwitchOverlay(true, startName + ' 已就绪 ✅'); return; }}
      // Detect failure: still exited after >20s
      if (_swState.elapsed > 20) {{
        var failed = containers.find(function(c) {{
          return c.name === startName && (c.status === 'exited' || c.status === 'not_found');
        }});
        if (failed) {{ _completeSwitchOverlay(false, startName + ' 启动失败'); return; }}
      }}
    }}
  }}).catch(function() {{ /* blip, ignore */ }});
}}

function _completeSwitchOverlay(success, msg) {{
  if (!_swState) return;
  clearInterval(_swState.timerInterval);
  clearInterval(_swState.pollInterval);
  _swState = null;

  var orb = document.querySelector('.sw-orb-core');
  if (success) {{
    document.getElementById('sw-title').textContent = '✅ 切换完成';
    document.getElementById('sw-detail').textContent = msg;
    document.getElementById('sw-timer').textContent = '';
    document.getElementById('sw-progress-bar').style.width = '100%';
    document.getElementById('sw-progress-bar').style.background = '#22c55e';
    if (orb) orb.style.background = 'radial-gradient(circle,#22c55e 0%,#14532d 60%,transparent 100%)';
    setTimeout(dismissSwitchOverlay, 3500);
  }} else {{
    document.getElementById('sw-title').textContent = '❌ 切换失败';
    document.getElementById('sw-detail').textContent = msg;
    document.getElementById('sw-timer').textContent = '';
    document.getElementById('sw-progress-bar').style.background = '#ef4444';
    if (orb) orb.style.background = 'radial-gradient(circle,#ef4444 0%,#7f1d1d 60%,transparent 100%)';
    // Leave overlay open so user can read the error and choose next step
  }}
  if (typeof loadContainers === 'function') setTimeout(loadContainers, 1000);
}}

function dismissSwitchOverlay() {{
  if (_swState) {{
    clearInterval(_swState.timerInterval);
    clearInterval(_swState.pollInterval);
    _swState = null;
  }}
  document.getElementById('sw-overlay').classList.remove('active');
}}

// Legacy alias (called from ctrlContainer / switchModel)
var dismissSwitchBanner = dismissSwitchOverlay;
var _completeSwitchBanner = _completeSwitchOverlay;
// ── End global switching overlay ──────────────────────────────────────────

// Auto-refresh GPU widget on home and GPU pages
const AUTO_REFRESH_PAGES = ['/', '/gpu'];
if (AUTO_REFRESH_PAGES.includes(window.location.pathname)) {{
  setInterval(() => {{
    fetch('/status').then(r => r.json()).then(updateGpuWidget).catch(() => {{}});
  }}, 10000);
}}
function updateGpuWidget(d) {{
  const el = id => document.getElementById(id);
  if (!d) return;
  if (d.vram_used_mb !== undefined && d.vram_total_mb) {{
    const used = d.vram_used_mb, total = d.vram_total_mb;
    const pct = Math.round(used / total * 100);
    if (el('vram-used')) el('vram-used').textContent = (used/1024).toFixed(1) + ' GB';
    if (el('vram-free')) el('vram-free').textContent = ((total-used)/1024).toFixed(1) + ' GB';
    if (el('vram-pct'))  el('vram-pct').textContent  = pct + '%';
    if (el('vram-bar'))  el('vram-bar').style.width   = pct + '%';
  }}
  if (d.gpu_util_pct !== null && d.gpu_util_pct !== undefined) {{
    if (el('gpu-util'))  el('gpu-util').textContent  = d.gpu_util_pct + '%';
  }}
  if (d.gpu_temp_c !== null && d.gpu_temp_c !== undefined) {{
    if (el('gpu-temp'))  el('gpu-temp').textContent  = d.gpu_temp_c + '°C';
  }}
  if (d.power_w !== null && d.power_w !== undefined) {{
    var pstr = d.power_w + ' W';
    if (d.power_limit_w) pstr += ' / ' + d.power_limit_w + ' W';
    if (el('gpu-power')) el('gpu-power').textContent = pstr;
  }}
  // Update dependency alert
  if (d.dependencies && d.dependencies._overall !== 'ok') {{
    showDependencyAlert(d.dependencies);
  }}
}}
function showDependencyAlert(deps) {{
  const el = document.getElementById('dependency-alert');
  if (!el || !deps) return;

  let html = '<div class="card" style="margin-bottom:16px;border:1px solid #dc2626;background:rgba(220,38,38,0.08)">';
  html += '<h2 style="margin-top:0;color:#dc2626">⚠️ 系统依赖异常</h2>';
  // Models issues (most critical)
  if (deps.models && (deps.models.issues || deps.models.warnings)) {{
    html += '<h3>📦 模型</h3><ul>';
    deps.models.issues.forEach(i => html += `<li style="color:#dc2626">${{i}}</li>`);
    deps.models.warnings.forEach(w => html += `<li style="color:#d97706">${{w}}</li>`);
    html += '</ul>';
  }}
  // Env issues
  if (deps.env && (deps.env.issues || deps.env.warnings)) {{
    html += '<h3>📋 配置</h3><ul>';
    deps.env.issues.forEach(i => html += `<li style="color:#dc2626">${{i}}</li>`);
    deps.env.warnings.forEach(w => html += `<li style="color:#d97706">${{w}}</li>`);
    html += '</ul>';
  }}
  // Data issues
  if (deps.data && (deps.data.issues || deps.data.warnings)) {{
    html += '<h3>🗄️ 数据目录</h3><ul>';
    deps.data.issues.forEach(i => html += `<li style="color:#dc2626">${{i}}</li>`);
    deps.data.warnings.forEach(w => html += `<li style="color:#d97706">${{w}}</li>`);
    html += '</ul>';
  }}
  // Docker issues
  if (deps.docker && deps.docker.issues) {{
    html += '<h3>🐳 Docker</h3><ul>';
    deps.docker.issues.forEach(i => html += `<li style="color:#dc2626">${{i}}</li>`);
    html += '</ul>';
  }}
  html += '<p style="font-size:13px;color:var(--text-dim);margin-bottom:0">运行 <code>./paas-controller.sh check-deps</code> 获取详细信息。</p>';
  html += '</div>';
  el.innerHTML = html;
  el.style.display = 'block';
}}
// Initial load
// Initial load
fetch('/status').then(r => r.json()).then(updateGpuWidget).catch(() => {{}});
// ── Global cookie alert ───────────────────────────────────────────────────
function _fmtCookieAge(hours) {{
  if (hours === null || hours === undefined) return '未知';
  var m = Math.round(hours * 60);
  if (m < 1) return '刚刚';
  if (m < 60) return m + ' 分钟前';
  var h = Math.floor(m / 60), mm = m % 60;
  return mm > 0 ? h + ' 小时 ' + mm + ' 分钟前' : h + ' 小时前';
}}
function _checkCookieAlert() {{
  fetch('/api/cookie-status').then(r => r.json()).then(d => {{
    const el = document.getElementById('cookie-alert');
    if (!el || !d.enabled) {{ if (el) el.style.display='none'; return; }}
    if (!d.file_exists || (d.cookie_age_hours !== null && d.cookie_age_hours > 24)) {{
      const msg = d.file_exists ? 'YouTube cookies 可能已过期（' + _fmtCookieAge(d.cookie_age_hours) + '刷新）' : 'YouTube cookies 文件不存在';
      const vnc = 'http://' + location.hostname + ':6901/vnc.html';
      el.innerHTML = '<div class="card" style="margin-bottom:16px;border:1px solid #f59e0b;background:rgba(245,158,11,0.08);padding:12px 16px">'
        + '<span style="color:#f59e0b;font-weight:600">⚠️ ' + msg + '</span>'
        + ' &nbsp;<a href="' + vnc + '" target="_blank" style="color:var(--accent)">打开 noVNC 登录 YouTube →</a>'
        + '</div>';
      el.style.display = 'block';
    }} else {{
      el.style.display = 'none';
    }}
  }}).catch(() => {{}});
}}
_checkCookieAlert();
setInterval(_checkCookieAlert, 60000);
</script>
</body>
</html>""")


# ── /status  (JSON API used by UI widgets) ───────────────────────────────────
def _check_dependencies_sync() -> dict:
    """Synchronous dependency health check for all system components."""
    import os
    from pathlib import Path

    deps = {
        "env": {"ok": True, "issues": [], "warnings": []},
        "models": {"ok": True, "issues": [], "warnings": [], "total_size_gb": 0},
        "data": {"ok": True, "issues": [], "warnings": []},
        "docker": {"ok": True, "issues": []},
        "gpu": {"ok": True, "issues": []},
    }

    models_root = Path(MODELS_ROOT)

    # 1. Environment — check via env vars (container doesn't have .env file)
    if not os.environ.get("MODELS_ROOT"):
        deps["env"]["ok"] = False
        deps["env"]["issues"].append("MODELS_ROOT 未设置")
    if not os.environ.get("LITELLM_API_KEY") and not os.environ.get("LITELLM_BASE_URL"):
        deps["env"]["warnings"].append("LITELLM_BASE_URL / LITELLM_API_KEY 未配置")

    # 2. Models directory
    if not models_root.exists():
        deps["models"]["ok"] = False
        deps["models"]["issues"].append(f"模型目录不存在: {models_root}")
    else:
        # Compute total size
        try:
            total_bytes = sum(f.stat().st_size for f in models_root.rglob("*") if f.is_file())
            deps["models"]["total_size_gb"] = round(total_bytes / (1024**3), 2)
        except Exception:
            pass

        # Check vLLM model
        vllm_model = models_root / "qwen2.5-32b-instruct-awq"
        if not vllm_model.exists():
            deps["models"]["ok"] = False
            deps["models"]["issues"].append("vLLM 生产模型缺失: qwen2.5-32b-instruct-awq")
        elif not (vllm_model / "config.json").exists():
            deps["models"]["ok"] = False
            deps["models"]["issues"].append("vLLM 模型不完整 (缺少 config.json)")

    # 3. Data directory — skip in container (data/ is on host, not mounted into webapp)

    # 4. Docker
    try:
        import docker
        dc = docker.from_env()
        dc.ping()
    except Exception as e:
        deps["docker"]["ok"] = False
        deps["docker"]["issues"].append(f"Docker 连接失败: {str(e)[:50]}...")

    # 5. GPU (if nvidia-smi exists in container)
    try:
        # We can't reliably run nvidia-smi from within webapp container unless it has GPU access
        # So we skip GPU check here; it's covered by status API anyway
        pass
    except Exception:
        pass

    # Overall status
    all_ok = all(d["ok"] for d in [deps["env"], deps["models"], deps["data"], deps["docker"]])
    deps["_overall"] = "ok" if all_ok else "error" if any(issue for k in ["env", "models", "data", "docker"] for issue in deps[k]["issues"]) else "warning"

    return deps


def _fetch_status_sync() -> dict:
    """Blocking Docker + nvidia-smi query — called via asyncio.to_thread."""
    # Run dependency check first
    try:
        deps = _check_dependencies_sync()
    except Exception as e:
        deps = {"_overall": "error", "error": str(e)}

    result = {
        "vram_used_mb": None, "vram_free_mb": None, "vram_total_mb": None,
        "gpu_util_pct": None, "gpu_temp_c": None,
        "power_w": None, "power_limit_w": None,
        "gpu_name": None, "driver_version": None,
        "gpu_processes": [],
        "containers": [],
        "dependencies": deps,
    }
    try:
        dc = docker.from_env()

        # ── GPU stats via nvidia-smi (try any vllm container first, fall back to ai_whisper) ──
        _GPU_QUERY_CONTAINERS = ["ai_vllm_qwen", "ai_vllm_gemma", "ai_whisper"]
        try:
            gpu_container = None
            for cname in _GPU_QUERY_CONTAINERS:
                try:
                    cand = dc.containers.get(cname)
                    if cand.status == "running":
                        gpu_container = cand
                        break
                except Exception:
                    pass

            if gpu_container:
                # Full GPU stats
                gpu_out = gpu_container.exec_run(
                    "nvidia-smi --query-gpu=name,driver_version,temperature.gpu,"
                    "utilization.gpu,memory.used,memory.free,memory.total,"
                    "power.draw,power.limit --format=csv,noheader,nounits",
                    stdout=True, stderr=False
                ).output.decode().strip()
                parts = [p.strip() for p in gpu_out.split(",")]
                if len(parts) >= 9:
                    result.update(
                        gpu_name=parts[0],
                        driver_version=parts[1],
                        gpu_temp_c=int(parts[2]),
                        gpu_util_pct=int(parts[3]),
                        vram_used_mb=int(parts[4]),
                        vram_free_mb=int(parts[5]),
                        vram_total_mb=int(parts[6]),
                        power_w=round(float(parts[7]), 1),
                        power_limit_w=round(float(parts[8]), 1),
                    )

                # Per-process GPU memory
                proc_out = gpu_container.exec_run(
                    "nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv,noheader",
                    stdout=True, stderr=False
                ).output.decode().strip()
                procs = []
                for line in proc_out.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    p = [x.strip() for x in line.split(",")]
                    if len(p) >= 3:
                        mem_str = p[1].replace("MiB", "").strip()
                        procs.append({
                            "pid": p[0],
                            "name": p[2],
                            "mem_mb": int(mem_str) if mem_str.isdigit() else 0,
                        })
                result["gpu_processes"] = procs
        except Exception:
            pass

        # ── Container stats (parallel, 2 s timeout per container) ──
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        def _fetch_one_container(name: str) -> dict:
            entry = {"name": name, "status": "not found",
                     "cpu_pct": None, "mem_mb": None, "mem_limit_mb": None}
            try:
                c = dc.containers.get(name)
                entry["status"] = c.status
                if c.status == "running":
                    try:
                        stats = c.stats(stream=False)
                        # CPU %
                        try:
                            cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - \
                                        stats["precpu_stats"]["cpu_usage"]["total_usage"]
                            sys_delta = stats["cpu_stats"]["system_cpu_usage"] - \
                                        stats["precpu_stats"]["system_cpu_usage"]
                            num_cpus  = stats["cpu_stats"]["online_cpus"]
                            if sys_delta > 0:
                                entry["cpu_pct"] = round(cpu_delta / sys_delta * num_cpus * 100, 1)
                        except Exception:
                            pass
                        # Memory
                        try:
                            mem = stats["memory_stats"]
                            cache = mem.get("stats", {}).get("cache", 0)
                            used = mem["usage"] - cache
                            entry["mem_mb"]       = round(used / 1024 / 1024, 1)
                            entry["mem_limit_mb"] = round(mem["limit"] / 1024 / 1024, 1)
                        except Exception:
                            pass
                    except Exception:
                        # stats() blocked or failed (container in transition) — skip metrics
                        pass
            except docker.errors.NotFound:
                pass
            return entry

        with ThreadPoolExecutor(max_workers=len(GPU_MANAGED_CONTAINERS)) as pool:
            futures = {pool.submit(_fetch_one_container, n): n for n in GPU_MANAGED_CONTAINERS}
            for fut, name in futures.items():
                try:
                    result["containers"].append(fut.result(timeout=2))
                except (FuturesTimeout, Exception):
                    # Timed out or errored — return minimal entry so UI doesn't block
                    result["containers"].append({"name": name, "status": "unknown",
                                                 "cpu_pct": None, "mem_mb": None,
                                                 "mem_limit_mb": None})

    except Exception:
        pass
    return result


@app.get("/status")
async def status():
    try:
        result = await asyncio.wait_for(asyncio.to_thread(_fetch_status_sync), timeout=5.0)
    except asyncio.TimeoutError:
        result = {
            "vram_used_mb": None, "vram_free_mb": None, "vram_total_mb": None,
            "gpu_util_pct": None, "gpu_temp_c": None,
            "power_w": None, "power_limit_w": None,
            "gpu_name": None, "driver_version": None,
            "gpu_processes": [],
            "containers": [{"name": n, "status": "unknown", "cpu_pct": None,
                             "mem_mb": None, "mem_limit_mb": None}
                            for n in GPU_MANAGED_CONTAINERS],
            "dependencies": {},
            "_error": "status fetch timed out (system busy)",
        }
    return JSONResponse(result)


@app.get("/api/gpu-status-lite")
async def gpu_status_lite():
    """Lightweight container status — no stats() calls, responds in <200ms.

    Used by the global switching banner to poll for completion without
    triggering the heavy docker stats() calls that block during transitions.
    """
    def _lite():
        try:
            dc = docker.from_env()
            out = []
            for name in GPU_MANAGED_CONTAINERS:
                try:
                    c = dc.containers.get(name)
                    out.append({"name": name, "status": c.status})
                except docker.errors.NotFound:
                    out.append({"name": name, "status": "not_found"})
            return {"containers": out}
        except Exception as e:
            return {"containers": [], "error": str(e)}

    result = await asyncio.to_thread(_lite)
    return JSONResponse(result)


@app.get("/api/cookie-status")
async def cookie_status():
    """Return cookie file status + cookie-manager health (if reachable)."""
    cookie_path = Path(YTDLP_COOKIES_PATH) if YTDLP_COOKIES_PATH else None
    result = {
        "enabled": bool(YTDLP_COOKIES_PATH),
        "file_exists": cookie_path.is_file() if cookie_path else False,
        "cookie_age_hours": None,
        "manager": None,
    }
    if result["file_exists"]:
        mtime = cookie_path.stat().st_mtime
        result["cookie_age_hours"] = round((time.time() - mtime) / 3600, 1)

    # Try to reach cookie-manager health API (may not be running)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://ai_cookie_manager:6902/health", timeout=2.0
            )
            if resp.status_code == 200:
                result["manager"] = resp.json()
    except Exception:
        pass  # cookie-manager not running — that's fine

    return JSONResponse(result)


@app.post("/api/cookie-refresh")
async def cookie_refresh_proxy():
    """Proxy to cookie-manager POST /refresh endpoint."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://ai_cookie_manager:6902/refresh", timeout=60.0
            )
            return JSONResponse(resp.json())
    except Exception as e:
        return JSONResponse(
            {"success": False, "message": f"Cookie Manager 未运行或不可达: {e}"},
            status_code=502,
        )


@app.get("/api/media-dirs")
async def media_dirs(max_depth: int = 3, max_dirs: int = 300):
    """Recursively scan MEDIA_ROOT up to max_depth levels (default 3, cap 300 dirs)."""
    if not MEDIA_ROOT or not Path(MEDIA_ROOT).is_dir():
        return JSONResponse({"configured": False, "dirs": []})

    root = Path(MEDIA_ROOT)
    dirs: list[dict] = []

    def _scan(path: Path, depth: int, rel_prefix: str) -> None:
        if depth > max_depth or len(dirs) >= max_dirs:
            return
        try:
            children = sorted(path.iterdir())
        except PermissionError:
            return
        for child in children:
            if len(dirs) >= max_dirs:
                break
            if not child.is_dir() or child.name.startswith("."):
                continue
            rel = f"{rel_prefix}/{child.name}" if rel_prefix else child.name
            dirs.append({"path": rel, "writable": os.access(child, os.W_OK), "depth": depth})
            _scan(child, depth + 1, rel)

    _scan(root, 0, "")
    writable = os.access(MEDIA_ROOT, os.W_OK)
    truncated = len(dirs) >= max_dirs
    return JSONResponse({"configured": True, "writable": writable, "dirs": dirs, "truncated": truncated})


# ── /  (Home) ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home():
    body = """
<div id="dependency-alert" style="display:none;"></div>

<div class="card">
  <h2>服务状态</h2>
  <div class="gpu-grid">
    <div class="gpu-stat"><div class="val" id="vram-used">—</div><div class="lbl">显存已用</div></div>
    <div class="gpu-stat"><div class="val" id="vram-free">—</div><div class="lbl">显存剩余</div></div>
  </div>
  <div class="vram-bar-wrap"><div class="vram-bar" id="vram-bar" style="width:0%"></div></div>
  <div style="font-size:12px;color:var(--text-dim);text-align:right;margin-top:4px">
    已用 <span id="vram-pct">—</span> / 24 GB  &nbsp;·&nbsp; 每 10s 自动刷新
  </div>
</div>
<div class="service-grid">
  <a class="service-card" href="/subtitle">
    <div class="icon">🎬</div>
    <div class="title">字幕生成</div>
    <div class="desc">YouTube 链接 或 上传视频 → .srt 字幕</div>
  </a>
  <a class="service-card" href="/translate">
    <div class="icon">🌐</div>
    <div class="title">文本翻译</div>
    <div class="desc">任意文本 → 目标语言</div>
  </a>
  <a class="service-card" href="/comfyui">
    <div class="icon">🖼️</div>
    <div class="title">文生图</div>
    <div class="desc">文本提示词 → 图像（ComfyUI）</div>
  </a>
  <a class="service-card" href="/comfyui">
    <div class="icon">🎥</div>
    <div class="title">文生视频</div>
    <div class="desc">文本提示词 → 视频（ComfyUI）</div>
  </a>
  <a class="service-card" href="/comfyui">
    <div class="icon">🧑</div>
    <div class="title">数字人</div>
    <div class="desc">图像驱动数字人（ComfyUI）</div>
  </a>
  <a class="service-card" href="/gpu">
    <div class="icon">⚡</div>
    <div class="title">GPU 控制</div>
    <div class="desc">查看显存 · 启停容器</div>
  </a>
</div>
"""
    return page("首页", "/", body)


# ── /subtitle ────────────────────────────────────────────────────────────────
@app.get("/subtitle", response_class=HTMLResponse)
async def subtitle_page():
    body = """
<div class="card">
  <h2>字幕生成</h2>
  <p style="font-size:13px;color:var(--text-dim);margin-bottom:16px">
    优先使用 YouTube 字幕（无需 GPU）；无字幕时自动用 Whisper 转录。
  </p>
  <div id="sub-cookie-hint" style="font-size:12px;margin-bottom:14px;display:none"></div>

  <div class="form-group">
    <label>YouTube 链接（可选，优先使用）</label>
    <input type="url" id="yt-url" placeholder="https://www.youtube.com/watch?v=...">
  </div>

  <div class="form-group">
    <label>或上传视频 / 音频文件</label>
    <label class="file-drop" id="drop-zone" for="file-input">
      📁 点击选择文件，或拖拽到此处
      <span id="file-name" style="display:block;margin-top:6px;color:var(--accent)"></span>
    </label>
    <input type="file" id="file-input" accept="video/*,audio/*,.mp4,.mkv,.mp3,.wav,.m4a">
  </div>

  <div class="form-group">
    <label>目标翻译语言（留空则只转录，不翻译）</label>
    <select id="target-lang">
      <option value="">— 只转录，不翻译 —</option>
      <option value="中文">中文</option>
      <option value="English">English</option>
      <option value="日本語">日本語</option>
      <option value="한국어">한국어</option>
      <option value="Español">Español</option>
      <option value="Français">Français</option>
    </select>
  </div>

  <button class="btn btn-primary" id="sub-btn" onclick="runSubtitle()">
    ▶ 生成字幕
  </button>

  <div class="result-box" id="sub-result"></div>
</div>

<script>
// File input display
document.getElementById('file-input').addEventListener('change', e => {
  const f = e.target.files[0];
  document.getElementById('file-name').textContent = f ? f.name : '';
});

async function runSubtitle() {
  const url  = document.getElementById('yt-url').value.trim();
  const file = document.getElementById('file-input').files[0];
  const lang = document.getElementById('target-lang').value;
  const btn  = document.getElementById('sub-btn');
  const res  = document.getElementById('sub-result');

  if (!url && !file) { alert('请输入 YouTube 链接或上传文件'); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 处理中...';
  res.className = 'result-box visible';
  res.textContent = '正在处理，请稍候…';

  try {
    const fd = new FormData();
    if (url)  fd.append('yt_url',  url);
    if (file) fd.append('file',    file);
    if (lang) fd.append('target_lang', lang);

    const r = await fetch('/api/subtitle', { method: 'POST', body: fd });
    const d = await r.json();
    res.textContent = d.error ? '❌ ' + d.error : d.result;
  } catch(e) {
    res.textContent = '❌ 请求失败: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '▶ 生成字幕';
  }
}
// Cookie status hint for subtitle page
fetch('/api/cookie-status').then(r => r.json()).then(d => {
  const el = document.getElementById('sub-cookie-hint');
  if (!el || !d.enabled) return;
  el.style.display = 'block';
  function fAge(h) {
    if (h === null) return '未知';
    var m = Math.round(h * 60);
    if (m < 1) return '刚刚';
    if (m < 60) return m + ' 分钟前';
    var hh = Math.floor(m / 60), mm = m % 60;
    return mm > 0 ? hh + ' 小时 ' + mm + ' 分钟前' : hh + ' 小时前';
  }
  if (d.file_exists && d.cookie_age_hours <= 24) {
    el.style.color = '#22c55e';
    el.innerHTML = '🍪 YouTube 已登录（cookies ' + fAge(d.cookie_age_hours) + '刷新），可访问受限视频';
  } else if (d.file_exists) {
    el.style.color = '#f59e0b';
    el.innerHTML = '⚠️ YouTube cookies 可能已过期（' + fAge(d.cookie_age_hours) + '刷新）。<a href="http://' + location.hostname + ':6901/vnc.html" target="_blank" style="color:var(--accent)">重新登录</a>';
  } else {
    el.style.color = 'var(--text-dim)';
    el.innerHTML = '🍪 未检测到 YouTube cookies。<a href="http://' + location.hostname + ':6901/vnc.html" target="_blank" style="color:var(--accent)">登录 YouTube</a> 可解锁受限视频';
  }
}).catch(() => {});
</script>
"""
    return page("字幕生成", "/subtitle", body)


@app.post("/api/subtitle")
async def api_subtitle(
    yt_url: str = Form(default=""),
    target_lang: str = Form(default=""),
    file: UploadFile = File(default=None),
):
    transcript = ""

    # Track A: try yt-dlp for YouTube subtitles
    if yt_url:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cmd = _ytdlp_base_cmd() + [
                    "--write-auto-sub", "--write-sub",
                    "--sub-lang", "en,zh,zh-Hans",
                    "--skip-download", "--output", f"{tmp}/sub",
                    yt_url
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                srt_files = list(Path(tmp).glob("*.vtt")) + list(Path(tmp).glob("*.srt"))
                if srt_files:
                    raw = srt_files[0].read_text(encoding="utf-8", errors="ignore")
                    # Strip VTT/SRT markup to plain text
                    import re
                    lines = [l.strip() for l in raw.splitlines()
                             if l.strip() and not re.match(r'^[\d:.,\-\> ]+$', l)
                             and not l.startswith("WEBVTT") and not l.isdigit()]
                    transcript = "\n".join(lines)
        except Exception as e:
            pass  # Fall through to Whisper

    # Track B: Whisper STT (if no YouTube subtitle found)
    if not transcript:
        audio_path = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                if yt_url:
                    # Download audio from YouTube
                    out_path = f"{tmp}/audio.%(ext)s"
                    cmd = _ytdlp_base_cmd() + [
                        "-x", "--audio-format", "mp3",
                        "--output", out_path, yt_url
                    ]
                    subprocess.run(cmd, capture_output=True, timeout=300)
                    mp3_files = list(Path(tmp).glob("*.mp3"))
                    if mp3_files:
                        audio_path = str(mp3_files[0])
                elif file:
                    suffix = Path(file.filename).suffix or ".mp4"
                    tmp_in = f"{tmp}/input{suffix}"
                    with open(tmp_in, "wb") as f_out:
                        f_out.write(await file.read())
                    # Extract audio with ffmpeg
                    audio_path = f"{tmp}/audio.wav"
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", tmp_in, "-ar", "16000",
                         "-ac", "1", "-f", "wav", audio_path],
                        capture_output=True, timeout=120
                    )

                if audio_path and Path(audio_path).exists():
                    async with httpx.AsyncClient(timeout=300) as client:
                        with open(audio_path, "rb") as af:
                            r = await client.post(
                                f"{WHISPER_BASE_URL}/audio/transcriptions",
                                files={"file": (Path(audio_path).name, af, "audio/wav")},
                                data={"model": WHISPER_MODEL},
                            )
                        if r.status_code == 200:
                            transcript = r.json().get("text", "")
                        else:
                            return JSONResponse({"error": f"Whisper 错误 {r.status_code}: {r.text[:200]}"})
                else:
                    return JSONResponse({"error": "无法获取音频（YouTube 下载失败或文件无效）"})
        except Exception as e:
            return JSONResponse({"error": f"转录失败: {str(e)}"})

    if not transcript:
        return JSONResponse({"error": "未能提取任何文本"})

    # Translation (optional)
    if target_lang and transcript:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    f"{LITELLM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {LITELLM_API_KEY}",
                             "Content-Type": "application/json"},
                    json={
                        "model": LLM_MODEL,
                        "messages": [
                            {"role": "system", "content":
                             f"You are a professional translator. Translate the following text to {target_lang}. "
                             "Output only the translation, no commentary."},
                            {"role": "user", "content": transcript}
                        ],
                        "max_tokens": 4096,
                    }
                )
            if r.status_code == 200:
                translated = r.json()["choices"][0]["message"]["content"]
                result = f"【原文】\n{transcript}\n\n【{target_lang} 译文】\n{translated}"
            else:
                result = f"【转录原文（翻译失败）】\n{transcript}"
        except Exception as e:
            result = f"【转录原文（翻译异常: {e}）】\n{transcript}"
    else:
        result = transcript

    return JSONResponse({"result": result})


# ── /download ────────────────────────────────────────────────────────────────
@app.get("/download", response_class=HTMLResponse)
async def download_page():
    body = """
<div class="card">
  <h2>媒体下载</h2>
  <p style="font-size:13px;color:var(--text-dim);margin-bottom:16px">
    支持 YouTube、B站、Twitter/X、Instagram、Facebook、TikTok 等 1000+ 平台。
  </p>
  <div id="dl-media-alert" style="display:none"></div>
  <div id="sub-cookie-hint" style="font-size:12px;margin-bottom:14px;display:none"></div>

  <!-- URL + probe -->
  <div style="display:flex;gap:8px;margin-bottom:4px">
    <input type="url" id="dl-url" placeholder="粘贴任意视频链接…" style="flex:1" onblur="probeUrl()">
    <button class="btn btn-ghost" id="dl-probe-btn" onclick="probeUrl()" style="white-space:nowrap;font-size:12px">🔍 探测</button>
  </div>
  <div id="dl-probe-status" style="font-size:12px;color:var(--text-dim);margin-bottom:16px;min-height:18px"></div>

  <!-- ── Section 1: Video ── -->
  <div class="dl-section" id="sec-video">
    <div class="dl-section-header" onclick="toggleSection('video')">
      <span id="sec-video-icon">▼</span>
      <span style="font-weight:600">🎬 视频</span>
      <label onclick="event.stopPropagation()" style="margin-left:auto;font-size:12px;cursor:pointer">
        <input type="checkbox" id="dl-enable-video" checked onchange="toggleEnable('video')"> 启用
      </label>
    </div>
    <div id="sec-video-body" class="dl-section-body">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="form-group" style="margin:0">
          <label>分辨率</label>
          <select id="dl-resolution">
            <option value="best">最佳</option>
            <option value="1080" selected>1080p</option>
            <option value="720">720p</option>
            <option value="480">480p</option>
            <option value="360">360p</option>
          </select>
        </div>
        <div class="form-group" style="margin:0">
          <label>格式</label>
          <select id="dl-video-format">
            <option value="mp4" selected>MP4</option>
            <option value="mkv">MKV</option>
            <option value="webm">WebM</option>
          </select>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Section 2: Audio ── -->
  <div class="dl-section" id="sec-audio">
    <div class="dl-section-header" onclick="toggleSection('audio')">
      <span id="sec-audio-icon">▼</span>
      <span style="font-weight:600">🎵 音频</span>
      <label onclick="event.stopPropagation()" style="margin-left:auto;font-size:12px;cursor:pointer">
        <input type="checkbox" id="dl-enable-audio" onchange="toggleEnable('audio')"> 单独保存音频
      </label>
    </div>
    <div id="sec-audio-body" class="dl-section-body">
      <div class="form-group" style="margin:0">
        <label>音频格式</label>
        <select id="dl-audio-format">
          <option value="mp3" selected>MP3（兼容性最好）</option>
          <option value="m4a">M4A（AAC，高质量）</option>
          <option value="flac">FLAC（无损）</option>
          <option value="opus">Opus（体积最小）</option>
          <option value="wav">WAV（无损，体积大）</option>
        </select>
      </div>
    </div>
  </div>

  <!-- ── Section 3: Subtitles ── -->
  <div class="dl-section" id="sec-subs">
    <div class="dl-section-header" onclick="toggleSection('subs')">
      <span id="sec-subs-icon">▼</span>
      <span style="font-weight:600">📄 字幕</span>
      <label onclick="event.stopPropagation()" style="margin-left:auto;font-size:12px;cursor:pointer">
        <input type="checkbox" id="dl-enable-subs" checked onchange="toggleEnable('subs')"> 启用
      </label>
    </div>
    <div id="sec-subs-body" class="dl-section-body">
      <div id="dl-subs-ai-hint" style="display:none;font-size:12px;padding:8px 10px;border-radius:6px;background:rgba(245,158,11,0.12);border:1px solid #f59e0b;margin-bottom:10px">
        ⚠️ 此内容无内嵌字幕，启用字幕将使用 Whisper AI 自动生成。
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">
        <div class="form-group" style="margin:0">
          <label>语言</label>
          <select id="dl-sub-lang">
            <option value="zh,zh-Hans,zh-Hant,en">中英文（推荐）</option>
            <option value="zh,zh-Hans,zh-Hant">仅中文</option>
            <option value="en">仅英文</option>
            <option value="ja">日语</option>
            <option value="ko">韩语</option>
            <option value="all">全部语言</option>
          </select>
        </div>
        <div style="display:flex;flex-direction:column;gap:6px;justify-content:flex-end">
          <label style="font-size:12px;cursor:pointer">
            <input type="checkbox" id="dl-embed-subs"> 嵌入字幕到视频
          </label>
          <label style="font-size:12px;cursor:pointer">
            <input type="checkbox" id="dl-write-subs" checked> 下载字幕文件 (.srt)
          </label>
          <label style="font-size:12px;cursor:pointer" id="dl-ai-transcribe-label">
            <input type="checkbox" id="dl-transcribe"> AI 生成字幕（Whisper）
          </label>
        </div>
      </div>
    </div>
  </div>

  <!-- Save dir + playlist -->
  <div style="display:grid;grid-template-columns:1fr auto;gap:12px;align-items:end;margin-top:8px;margin-bottom:4px">
    <div class="form-group" style="margin:0">
      <label>保存到</label>
      <select id="dl-dir"><option value="">加载中...</option></select>
    </div>
    <label style="font-size:12px;cursor:pointer;white-space:nowrap;padding-bottom:6px">
      <input type="checkbox" id="dl-playlist"> 下载整个播放列表
    </label>
  </div>
  <div id="dl-dir-hint" style="display:none;font-size:11px;color:var(--text-dim);margin-bottom:4px"></div>
  <div id="dl-dir-custom-wrap" style="display:none;margin-bottom:16px">
    <input type="text" id="dl-dir-custom" placeholder="手动输入相对路径，例如 tv/Doraemon/Season2"
      style="font-size:12px;padding:4px 8px" oninput="syncCustomDir()">
  </div>
  <div id="dl-dir-spacer" style="margin-bottom:16px"></div>

  <button class="btn btn-primary" id="dl-btn" onclick="startDownload()">📥 开始下载</button>

  <div id="dl-progress" style="display:none;margin-top:16px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
      <span class="ck-spin" style="font-size:18px">⟳</span>
      <span id="dl-status" style="font-size:14px;font-weight:600">准备中...</span>
      <span id="dl-pct" style="font-size:13px;color:var(--text-dim)"></span>
    </div>
    <div style="height:4px;background:var(--border);border-radius:2px;margin-bottom:8px;overflow:hidden">
      <div id="dl-bar" style="height:100%;width:0%;background:var(--accent);transition:width 0.3s;border-radius:2px"></div>
    </div>
    <pre id="dl-log" style="max-height:200px;overflow-y:auto;font-size:11px;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:8px;white-space:pre-wrap;color:var(--text-dim)"></pre>
  </div>
  <div id="dl-result" style="display:none;margin-top:16px"></div>
</div>

<style>
.ck-spin { display:inline-block; animation: ck-rotate 1s linear infinite; }
@keyframes ck-rotate { from { transform:rotate(0deg); } to { transform:rotate(360deg); } }
.dl-section { border:1px solid var(--border); border-radius:8px; margin-bottom:10px; overflow:hidden; }
.dl-section-header { display:flex; align-items:center; gap:8px; padding:10px 14px; cursor:pointer; background:var(--surface); font-size:13px; user-select:none; }
.dl-section-header:hover { background:var(--border); }
.dl-section-body { padding:12px 14px; }
.dl-section.disabled { opacity:0.45; pointer-events:none; }
.dl-section.disabled .dl-section-header { pointer-events:auto; }
</style>

<script>
// ── Section collapse/expand ──────────────────────────────────────────────────
const _sectionOpen = {video: true, audio: true, subs: true};
function toggleSection(s) {
  _sectionOpen[s] = !_sectionOpen[s];
  document.getElementById('sec-' + s + '-body').style.display = _sectionOpen[s] ? '' : 'none';
  document.getElementById('sec-' + s + '-icon').textContent = _sectionOpen[s] ? '▼' : '▶';
}
function toggleEnable(s) {
  const enabled = document.getElementById('dl-enable-' + s).checked;
  const sec = document.getElementById('sec-' + s);
  sec.classList.toggle('disabled', !enabled);
}
// Init: audio section closed by default (not enabled)
document.getElementById('sec-audio-body').style.display = 'none';
document.getElementById('sec-audio-icon').textContent = '▶';
_sectionOpen.audio = false;

// ── URL probe ────────────────────────────────────────────────────────────────
let _probeAbort = null;
let _lastProbedUrl = '';
async function probeUrl() {
  const url = document.getElementById('dl-url').value.trim();
  if (!url || url === _lastProbedUrl) return;
  _lastProbedUrl = url;
  if (_probeAbort) _probeAbort.abort();
  _probeAbort = new AbortController();
  const statusEl = document.getElementById('dl-probe-status');
  statusEl.textContent = '🔍 探测中...';
  statusEl.style.color = 'var(--text-dim)';
  try {
    const r = await fetch('/api/download/probe', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url}),
      signal: _probeAbort.signal,
    });
    const d = await r.json();
    if (d.error) { statusEl.textContent = '⚠️ ' + d.error; return; }

    // Video availability
    const secVideo = document.getElementById('sec-video');
    const enableVideoCb = document.getElementById('dl-enable-video');
    if (!d.has_video) {
      secVideo.classList.add('disabled');
      enableVideoCb.checked = false;
      secVideo.querySelector('.dl-section-header span:nth-child(2)').textContent = '🎬 视频（无视频流，已禁用）';
    } else {
      secVideo.classList.remove('disabled');
      enableVideoCb.checked = true;
      secVideo.querySelector('.dl-section-header span:nth-child(2)').textContent = '🎬 视频';
    }

    // Subtitle availability
    const aiHint = document.getElementById('dl-subs-ai-hint');
    const transcribeCb = document.getElementById('dl-transcribe');
    if (!d.has_subs) {
      aiHint.style.display = '';
      transcribeCb.checked = true;
    } else {
      aiHint.style.display = 'none';
      transcribeCb.checked = false;
    }

    // Playlist
    if (d.is_playlist) {
      document.getElementById('dl-playlist').checked = true;
    }

    // Status line
    const parts = [];
    if (d.title) parts.push(d.title.length > 50 ? d.title.slice(0, 50) + '…' : d.title);
    if (d.duration) parts.push(_fmtDuration(d.duration));
    if (d.uploader) parts.push(d.uploader);
    statusEl.textContent = parts.length ? '✅ ' + parts.join(' · ') : '✅ 探测成功';
    statusEl.style.color = '#22c55e';
  } catch(e) {
    if (e.name !== 'AbortError') { statusEl.textContent = '探测失败（可直接下载）'; statusEl.style.color = 'var(--text-dim)'; }
  }
}
function _fmtDuration(s) {
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), sec = s%60;
  if (h) return h + ':' + String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
  return m + ':' + String(sec).padStart(2,'0');
}

// ── Media dirs ───────────────────────────────────────────────────────────────
fetch('/api/media-dirs').then(r => r.json()).then(d => {
  const sel = document.getElementById('dl-dir');
  const alert = document.getElementById('dl-media-alert');
  if (!d.configured) {
    alert.style.display = 'block';
    alert.innerHTML = '<div class="card" style="border:1px solid #dc2626;background:rgba(220,38,38,0.08);padding:12px">❌ 未配置 MEDIA_ROOT。请在 <code>.env</code> 中设置 <code>MEDIA_ROOT=/mnt/truenas/media</code> 并重建容器。</div>';
    document.getElementById('dl-btn').disabled = true;
    return;
  }
  if (!d.writable) {
    alert.style.display = 'block';
    alert.innerHTML = '<div class="card" style="border:1px solid #f59e0b;background:rgba(245,158,11,0.08);padding:12px">⚠️ 媒体目录不可写。</div>';
  }
  sel.innerHTML = '';
  const rootOpt = document.createElement('option');
  rootOpt.value = '.'; rootOpt.textContent = '📂 / (根目录)';
  sel.appendChild(rootOpt);
  d.dirs.forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.path;
    const lock = item.writable ? '' : ' 🔒';
    const indent = '\\u00a0\\u00a0\\u00a0\\u00a0'.repeat(item.depth);
    const icon = item.depth === 0 ? '📁 ' : '└─ ';
    opt.textContent = indent + icon + item.path.split('/').pop() + lock;
    if (item.depth === 0) opt.style.fontWeight = '600';
    if (!item.writable) opt.style.color = '#999';
    sel.appendChild(opt);
  });
  // Truncated hint + manual input
  const hint = document.getElementById('dl-dir-hint');
  const customWrap = document.getElementById('dl-dir-custom-wrap');
  const spacer = document.getElementById('dl-dir-spacer');
  if (d.truncated) {
    hint.style.display = '';
    hint.textContent = '⚠️ 目录过多，仅显示前 ' + d.dirs.length + ' 个（深度3层）。如需更深的路径，请手动输入：';
    customWrap.style.display = '';
    spacer.style.display = 'none';
  } else {
    spacer.style.marginBottom = '16px';
  }
}).catch(() => {});

function syncCustomDir() {
  const val = document.getElementById('dl-dir-custom').value.trim();
  // When user types in custom box, override the select value on submit
  // (handled in startDownload by checking custom box first)
}

// ── Cookie hint ──────────────────────────────────────────────────────────────
fetch('/api/cookie-status').then(r => r.json()).then(d => {
  const el = document.getElementById('sub-cookie-hint');
  if (!el || !d.enabled) return;
  el.style.display = 'block';
  if (d.file_exists && d.cookie_age_hours <= 24) {
    el.style.color = '#22c55e';
    el.innerHTML = '🍪 YouTube 已登录，可下载受限视频';
  } else {
    el.style.color = 'var(--text-dim)';
    el.innerHTML = '🍪 未登录 YouTube。<a href="http://' + location.hostname + ':6901/vnc.html" target="_blank" style="color:var(--accent)">登录</a> 可解锁受限内容';
  }
}).catch(() => {});

// ── Start download ───────────────────────────────────────────────────────────
async function startDownload() {
  const url = document.getElementById('dl-url').value.trim();
  if (!url) { alert('请输入视频链接'); return; }

  const videoEnabled = document.getElementById('dl-enable-video').checked;
  const audioEnabled = document.getElementById('dl-enable-audio').checked;
  const subsEnabled  = document.getElementById('dl-enable-subs').checked;
  if (!videoEnabled && !audioEnabled && !subsEnabled) {
    alert('请至少启用一个下载项（视频/音频/字幕）');
    return;
  }

  // Determine primary download_type for backend
  let download_type = 'video';
  if (!videoEnabled && audioEnabled) download_type = 'audio';
  else if (!videoEnabled && !audioEnabled && subsEnabled) download_type = 'subs';

  const btn = document.getElementById('dl-btn');
  const prog = document.getElementById('dl-progress');
  const log = document.getElementById('dl-log');
  const status = document.getElementById('dl-status');
  const pct = document.getElementById('dl-pct');
  const bar = document.getElementById('dl-bar');
  const result = document.getElementById('dl-result');

  btn.disabled = true;
  btn.textContent = '⏳ 下载中...';
  prog.style.display = 'block';
  result.style.display = 'none';
  log.textContent = '';
  status.textContent = '正在启动下载...';
  pct.textContent = '';
  bar.style.width = '0%';

  try {
    const body = {
      url,
      download_type,
      video_enabled: videoEnabled,
      audio_enabled: audioEnabled,
      subs_enabled:  subsEnabled,
      resolution:    document.getElementById('dl-resolution').value,
      video_format:  document.getElementById('dl-video-format').value,
      audio_format:  document.getElementById('dl-audio-format').value,
      sub_lang:      document.getElementById('dl-sub-lang').value,
      embed_subs:    document.getElementById('dl-embed-subs').checked,
      write_subs:    document.getElementById('dl-write-subs').checked,
      ai_transcribe: document.getElementById('dl-transcribe').checked,
      playlist:      document.getElementById('dl-playlist').checked,
      save_dir:      (document.getElementById('dl-dir-custom').value.trim() || document.getElementById('dl-dir').value),
    };

    const resp = await fetch('/api/download', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const ev = JSON.parse(line.slice(6));
          if (ev.type === 'progress') {
            const m = ev.message.match(/(\\d+\\.?\\d*)%/);
            if (m) { bar.style.width = m[1] + '%'; pct.textContent = parseFloat(m[1]).toFixed(1) + '%'; status.textContent = '正在下载...'; }
            else { status.textContent = ev.message; pct.textContent = ''; }
            log.textContent += ev.message + '\\n';
            log.scrollTop = log.scrollHeight;
          } else if (ev.type === 'done') {
            bar.style.width = '100%'; pct.textContent = '100%'; status.textContent = '✅ 完成'; prog.style.display = 'none';
            let rhtml = '<div class="card" style="border:1px solid #22c55e;background:rgba(34,197,94,0.08);padding:12px"><strong>✅ 下载完成</strong><br>';
            if (ev.files && ev.files.length) { rhtml += '<ul style="margin:8px 0 0;padding-left:20px;font-size:13px">'; ev.files.forEach(f => rhtml += '<li>' + f + '</li>'); rhtml += '</ul>'; }
            rhtml += '<div style="font-size:12px;color:var(--text-dim);margin-top:6px">保存到: ' + ev.save_dir + '</div></div>';
            result.innerHTML = rhtml; result.style.display = 'block';
          } else if (ev.type === 'error') {
            prog.style.display = 'none';
            result.innerHTML = '<div class="card" style="border:1px solid #dc2626;background:rgba(220,38,38,0.08);padding:12px">❌ ' + ev.message + '</div>';
            result.style.display = 'block';
          }
        } catch(e) {}
      }
    }
  } catch(e) {
    prog.style.display = 'none';
    result.innerHTML = '<div class="card" style="border:1px solid #dc2626;background:rgba(220,38,38,0.08);padding:12px">❌ 请求失败: ' + e.message + '</div>';
    result.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = '📥 开始下载';
  }
}
</script>
"""
    return page("下载", "/download", body)


@app.post("/api/download/probe")
async def api_download_probe(request: Request):
    """Probe a URL with yt-dlp --dump-json to detect video/audio/subtitle availability."""
    data = await request.json()
    url = data.get("url", "").strip()
    if not url:
        return JSONResponse({"error": "URL required"}, status_code=400)

    cmd = _ytdlp_base_cmd() + [
        "--dump-json", "--no-playlist", "--skip-download",
        "--quiet", url,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
    except asyncio.TimeoutError:
        return JSONResponse({"error": "探测超时（20s），可直接尝试下载"})
    except Exception as e:
        return JSONResponse({"error": str(e)})

    raw_stdout = stdout.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        # Check if we still got valid JSON output despite non-zero exit
        # (yt-dlp sometimes exits non-zero on cookie warnings but still dumps info)
        if not raw_stdout or not raw_stdout.startswith("{"):
            err = stderr.decode("utf-8", errors="replace").strip()
            for line in err.splitlines():
                if "ERROR" in line:
                    err = line
                    break
            return JSONResponse({"error": err[:200] if err else "探测失败"})

    try:
        info = json.loads(raw_stdout)
    except Exception:
        return JSONResponse({"error": "无法解析探测结果"})

    # Detect video stream (any format with vcodec not 'none')
    formats = info.get("formats", [])
    has_video = any(
        f.get("vcodec", "none") not in ("none", None) for f in formats
    ) if formats else bool(info.get("vcodec") and info.get("vcodec") != "none")

    # Detect subtitles (automatic or manual)
    subs = info.get("subtitles", {})
    auto_subs = info.get("automatic_captions", {})
    has_subs = bool(subs) or bool(auto_subs)

    # Playlist detection
    is_playlist = info.get("_type") == "playlist" or bool(info.get("playlist_id"))

    return JSONResponse({
        "title":       info.get("title", ""),
        "uploader":    info.get("uploader", info.get("channel", "")),
        "duration":    info.get("duration"),
        "thumbnail":   info.get("thumbnail", ""),
        "has_video":   has_video,
        "has_audio":   True,   # virtually all sources have audio
        "has_subs":    has_subs,
        "is_playlist": is_playlist,
        "sub_langs":   list(subs.keys())[:10],
    })


@app.post("/api/download")
async def api_download(request: Request):
    """Download video/audio/subtitles via yt-dlp, stream progress via SSE."""
    data = await request.json()
    url = data.get("url", "").strip()
    download_type = data.get("download_type", "video")   # video | audio | subs
    resolution = data.get("resolution", "1080")
    video_format = data.get("video_format", "mp4")
    audio_format = data.get("audio_format", "mp3")
    sub_lang = data.get("sub_lang", "zh,zh-Hans,zh-Hant,en")
    embed_subs = data.get("embed_subs", False)
    write_subs = data.get("write_subs", True)
    ai_transcribe = data.get("ai_transcribe", False)
    playlist = data.get("playlist", False)
    save_dir = data.get("save_dir", ".")

    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    # Validate save path
    if not MEDIA_ROOT or not Path(MEDIA_ROOT).is_dir():
        return JSONResponse({"error": "MEDIA_ROOT not configured"}, status_code=500)

    target_dir = Path(MEDIA_ROOT) / save_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    # Security: ensure target is under MEDIA_ROOT
    try:
        target_dir.resolve().relative_to(Path(MEDIA_ROOT).resolve())
    except ValueError:
        return JSONResponse({"error": "Invalid save directory"}, status_code=400)

    # Check write permission
    if not os.access(target_dir, os.W_OK):
        return JSONResponse(
            {"error": f"目录 '{save_dir}' 无写入权限，请在 NAS 上检查目录权限 (chmod o+w)"},
            status_code=403,
        )

    async def event_stream():
        import re

        def sse(event_type: str, **kwargs):
            payload = json.dumps({"type": event_type, **kwargs})
            return f"data: {payload}\n\n"

        yield sse("progress", message=f"目标目录: {save_dir}")

        base_cmd = _ytdlp_base_cmd()
        playlist_flag = [] if playlist else ["--no-playlist"]
        output_tmpl = ["-o", str(target_dir / "%(title)s.%(ext)s")]
        files_created = []

        try:
            # Snapshot existing files before download to detect truly new files
            existing_files: set[str] = set()
            try:
                existing_files = {f.name for f in target_dir.iterdir() if f.is_file()}
            except Exception:
                pass

            # ── VIDEO ────────────────────────────────────────────────────
            if download_type == "video":
                yield sse("progress", message="正在下载视频...")
                fmt_map = {
                    "best": "bestvideo+bestaudio/best",
                    "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
                    "720":  "bestvideo[height<=720]+bestaudio/best[height<=720]",
                    "480":  "bestvideo[height<=480]+bestaudio/best[height<=480]",
                    "360":  "bestvideo[height<=360]+bestaudio/best[height<=360]",
                }
                fmt = fmt_map.get(resolution, fmt_map["1080"])
                cmd = base_cmd + [
                    "-f", fmt,
                    "--merge-output-format", video_format,
                    "--newline",
                ] + output_tmpl + playlist_flag
                if write_subs:
                    cmd += ["--write-auto-sub", "--write-sub", "--sub-lang", sub_lang]
                if embed_subs:
                    cmd += ["--embed-subs"]
                cmd.append(url)

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                last_error = ""
                async for line in proc.stdout:
                    text = line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    if text.startswith("ERROR:"):
                        last_error = text
                    pct_match = re.search(r'\[download\]\s+(\d+\.?\d*)%', text)
                    if pct_match:
                        yield sse("progress", message=f"下载中: {pct_match.group(1)}%")
                    elif "[download] Destination:" in text:
                        fname = text.split("Destination:")[-1].strip()
                        yield sse("progress", message=f"文件: {Path(fname).name}")
                    elif "[Merger]" in text or "Merging" in text:
                        yield sse("progress", message="合并音视频...")
                    elif "[EmbedSubtitle]" in text:
                        yield sse("progress", message="嵌入字幕...")
                    elif text.startswith("[download] 100%"):
                        yield sse("progress", message="下载完成，处理中...")
                await proc.wait()
                if proc.returncode != 0:
                    created = [f for f in target_dir.iterdir()
                               if f.is_file() and not f.name.startswith(".")]
                    if not created:
                        yield sse("error", message=last_error or "视频下载失败，请检查链接是否正确")
                        return

            # ── AUDIO ────────────────────────────────────────────────────
            elif download_type == "audio":
                yield sse("progress", message=f"正在提取音频 ({audio_format.upper()})...")
                cmd = base_cmd + [
                    "-f", "bestaudio/best",
                    "-x", "--audio-format", audio_format,
                    "--audio-quality", "0",
                    "--newline",
                ] + output_tmpl + playlist_flag + [url]

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                last_error = ""
                async for line in proc.stdout:
                    text = line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    if text.startswith("ERROR:"):
                        last_error = text
                    pct_match = re.search(r'\[download\]\s+(\d+\.?\d*)%', text)
                    if pct_match:
                        yield sse("progress", message=f"下载中: {pct_match.group(1)}%")
                    elif "[ExtractAudio]" in text:
                        yield sse("progress", message="提取音频...")
                    elif "[download] Destination:" in text:
                        fname = text.split("Destination:")[-1].strip()
                        yield sse("progress", message=f"文件: {Path(fname).name}")
                await proc.wait()
                if proc.returncode != 0:
                    created = [f for f in target_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
                    if not created:
                        yield sse("error", message=last_error or "音频下载失败，请检查链接是否正确")
                        return

            # ── SUBTITLES ONLY ───────────────────────────────────────────
            elif download_type == "subs":
                yield sse("progress", message=f"正在下载字幕 ({sub_lang})...")
                cmd = base_cmd + [
                    "--write-auto-sub", "--write-sub",
                    "--sub-lang", sub_lang,
                    "--skip-download",
                ] + output_tmpl + playlist_flag + [url]

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                async for line in proc.stdout:
                    text = line.decode("utf-8", errors="replace").strip()
                    if text:
                        yield sse("progress", message=text[:120])
                await proc.wait()

            # ── AI transcribe (stub — Whisper integration pending) ───────
            if ai_transcribe:
                yield sse("progress", message="AI 转录：正在调用 Whisper...")
                # TODO: POST to WHISPER_BASE_URL /v1/audio/transcriptions
                # For now, check if any audio/video file exists and call whisper
                yield sse("progress", message="AI 转录暂未完全集成，字幕文件已下载（如有）")

            # Collect newly created files
            for f in sorted(target_dir.iterdir()):
                if f.is_file() and not f.name.startswith(".") and f.name not in existing_files:
                    size_mb = f.stat().st_size / (1024 * 1024)
                    files_created.append(f"{f.name} ({size_mb:.1f} MB)")

            if not files_created:
                yield sse("error", message="未创建任何新文件，下载可能失败或文件已存在于目标目录")
                return

            yield sse("done", files=files_created, save_dir=str(save_dir))

        except Exception as e:
            yield sse("error", message=str(e))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── /translate ───────────────────────────────────────────────────────────────
@app.get("/translate", response_class=HTMLResponse)
async def translate_page():
    body = """
<div class="card">
  <h2>文本翻译</h2>
  <div class="form-group">
    <label>原文</label>
    <textarea id="src-text" rows="5" placeholder="输入要翻译的文本…"></textarea>
  </div>
  <div class="form-group">
    <label>目标语言</label>
    <select id="tgt-lang">
      <option value="中文">中文</option>
      <option value="English">English</option>
      <option value="日本語">日本語</option>
      <option value="한국어">한국어</option>
      <option value="Español">Español</option>
      <option value="Français">Français</option>
      <option value="Deutsch">Deutsch</option>
    </select>
  </div>
  <button class="btn btn-primary" id="tr-btn" onclick="runTranslate()">▶ 翻译</button>
  <div class="result-box" id="tr-result"></div>
</div>
<script>
async function runTranslate() {
  const text = document.getElementById('src-text').value.trim();
  const lang = document.getElementById('tgt-lang').value;
  const btn  = document.getElementById('tr-btn');
  const res  = document.getElementById('tr-result');
  if (!text) { alert('请输入要翻译的文本'); return; }
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 翻译中...';
  res.className = 'result-box visible';
  res.textContent = '正在翻译…';
  try {
    const r = await fetch('/api/translate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ text, target_lang: lang })
    });
    const d = await r.json();
    res.textContent = d.error ? '❌ ' + d.error : d.result;
  } catch(e) {
    res.textContent = '❌ 请求失败: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '▶ 翻译';
  }
}
</script>
"""
    return page("文本翻译", "/translate", body)


@app.post("/api/translate")
async def api_translate(request: Request):
    body = await request.json()
    text = body.get("text", "").strip()
    lang = body.get("target_lang", "中文")
    if not text:
        return JSONResponse({"error": "文本为空"})
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{LITELLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {LITELLM_API_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content":
                         f"You are a professional translator. Translate to {lang}. Output only the translation."},
                        {"role": "user", "content": text}
                    ],
                    "max_tokens": 4096,
                }
            )
        if r.status_code == 200:
            return JSONResponse({"result": r.json()["choices"][0]["message"]["content"]})
        return JSONResponse({"error": f"LLM 错误 {r.status_code}: {r.text[:200]}"})
    except Exception as e:
        return JSONResponse({"error": str(e)})


# ── /comfyui ─────────────────────────────────────────────────────────────────
COMFYUI_URL = os.getenv("COMFYUI_BASE_URL", "http://ai_comfyui:8188").replace(
    "ai_comfyui", "192.168.0.19"
)

@app.get("/comfyui", response_class=HTMLResponse)
async def comfyui_page():
    body = """
<div class="card">
  <h2>视觉生成 — ComfyUI</h2>
  <p style="font-size:13px;color:var(--text-dim);margin-bottom:16px">
    ComfyUI 是一个基于节点的图形工作流编辑器，支持文生图、文生视频和数字人驱动。
    <br>使用前需要在 GPU 控制页面先停止 vLLM，再启动 ComfyUI（两者不能同时运行）。
  </p>

  <div id="comfyui-status" style="margin-bottom:16px">
    <span class="badge badge-yellow">检测中…</span>
  </div>

  <div id="comfyui-actions" style="display:none;gap:10px;flex-wrap:wrap;margin-bottom:16px">
    <a href="http://192.168.0.19:8188" target="_blank" class="btn btn-primary">
      🎨 打开 ComfyUI 界面
    </a>
    <a href="/gpu" class="btn btn-ghost">
      ⚡ 去 GPU 页面
    </a>
  </div>

  <div id="comfyui-prompt" style="display:none;margin-bottom:16px">
    <div style="padding:16px;background:var(--bg);border:1px solid var(--border);border-radius:8px">
      <div style="font-size:14px;margin-bottom:8px">
        容器 <code style="font-family:monospace">ai_comfyui</code> 当前尚未启动，需要启动吗？
      </div>
      <div id="comfyui-prompt-msg" style="display:none;font-size:13px;color:var(--text-dim);margin-bottom:12px"></div>
      <div id="comfyui-progress" style="display:none">
        <div class="vram-bar-wrap" style="width:300px;margin-bottom:8px">
          <div class="vram-bar" id="comfyui-progress-bar" style="width:0%"></div>
        </div>
        <div id="comfyui-progress-text" style="font-size:12px;color:var(--text-dim)">准备中…</div>
      </div>
      <div id="comfyui-prompt-btns" style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-primary" onclick="autoStartComfyUI()" id="btn-comfyui-start">是的，启动 ComfyUI</button>
        <button class="btn btn-ghost" onclick="cancelComfyUIPrompt()">取消</button>
      </div>
    </div>
  </div>

  <div id="comfyui-actions-default" style="display:none;gap:10px;flex-wrap:wrap">
    <a href="http://192.168.0.19:8188" target="_blank" class="btn btn-primary">
      🎨 打开 ComfyUI 界面
    </a>
    <a href="/gpu" class="btn btn-ghost">
      ⚡ 去 GPU 页面
    </a>
    <button class="btn btn-ghost" onclick="autoStartComfyUI()">⚡ 一键切换 ComfyUI</button>
  </div>
</div>

<div class="card">
  <h2>内置工作流（开箱即用）</h2>
  <p style="font-size:13px;color:var(--text-dim);margin-bottom:16px">
    以下工作流已预置在 ComfyUI 容器内。下载 JSON 后拖入 ComfyUI 界面即可使用。
  </p>
  <div id="workflow-browser" style="display:flex;flex-direction:column;gap:20px">
    <div style="color:var(--text-dim);font-size:13px">加载工作流列表…</div>
  </div>
</div>
<div id="comfyui-model-paths-card" class="card" style="display:none">
  <h2>模型配置</h2>
  <div id="comfyui-model-paths-content"></div>
</div>

<div class="card">
  <h2>如何获取更多工作流</h2>
  <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">
    除了以上内置工作流外，如需更多工作流（图像放大、LoRA 等），可通过以下方式获取：
  </p>
  <ol style="font-size:13px;color:var(--text-dim);line-height:2.2;padding-left:20px">
    <li><strong>推荐：</strong>访问 <a href="https://comfyworkflows.com/" target="_blank" rel="noopener">ComfyWorkflows.com</a>，专门的 ComfyUI 工作流社区，每个工作流都有预览图和一键下载</li>
    <li><a href="https://opencomfy.io/" target="_blank" rel="noopener">OpenComfy.io</a> — ComfyUI 资源站，包含工作流和模型推荐</li>
    <li>YouTube / B站搜索 "ComfyUI workflow"，视频描述里常附 <code>.json</code> 下载链接</li>
  </ol>
  <p style="font-size:13px;color:var(--text-dim);margin-top:12px;padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:8px">
    <strong>导入方法：</strong>下载 <code>.json</code> → ComfyUI 右上角 ⚙️ → <strong>Load</strong>，或直接拖入页面。<br>
    <strong>提示：</strong>红色节点 = 缺少自定义节点，请先在 ComfyUI-Manager 中安装对应插件。
  </p>
</div>

<div class="card">
  <h2>生成的图片或视频在哪里看？</h2>
  <ol style="font-size:13px;color:var(--text-dim);line-height:2.2;padding-left:20px">
    <li><strong>ComfyUI 界面内查看：</strong>进入 ComfyUI 后，左侧默认面板会显示最新生成的图片预览。也可以点击左侧面板底部的小图标切换输出/历史记录</li>
    <li><strong>浏览器直接访问：</strong>图片生成后，在 <a href="http://192.168.0.19:8188/view?filename=comfyui_test_00001_.png&type=output" target="_blank">这个链接</a> 可直接打开（文件名随生成顺序变化）</li>
    <li><strong>服务器文件系统：</strong>所有输出图片保存在服务器上 <code>data/comfyui_workdir/output/</code>，可在本机浏览该目录</li>
  </ol>
</div>

<div class="card">
  <h2>使用说明</h2>
  <ol style="font-size:13px;color:var(--text-dim);line-height:2;padding-left:20px">
    <li>如果 ComfyUI 未启动，页面会提示是否需要一键切换；点击「启动」即可自动完成</li>
    <li>系统会自动停止 vLLM（如有需要），释放 GPU 显存，再启动 ComfyUI（约 60 秒）</li>
    <li>启动完成后，点击「打开 ComfyUI 界面」进入工作流编辑器</li>
    <li>在 ComfyUI 中选择或导入工作流，点击 Queue 提交生成任务</li>
    <li>使用完毕后，前往 <a href="/gpu" style="color:var(--accent)">GPU 控制页面</a>停止 ComfyUI，再启动 vLLM</li>
  </ol>
  <p style="font-size:12px;color:var(--warn);margin-top:12px">
    ⚠️ RTX 3090 24 GB 显存独占：vLLM 和 ComfyUI 不能同时运行，必须先停一个再启另一个。
  </p>
</div>

<script>
async function checkComfyUI() {
  var el = document.getElementById('comfyui-status');
  var promptDiv = document.getElementById('comfyui-prompt');
  var actionsDiv = document.getElementById('comfyui-actions');
  var actionsDefault = document.getElementById('comfyui-actions-default');
  try {
    var r = await fetch('/status');
    if (!r.ok) throw new Error('status error');
    var d = await r.json();
    var comfyui = (d.containers || []).find(function(c) { return c.name === 'ai_comfyui'; });
    var vllm = (d.containers || []).find(function(c) { return c.name.startsWith('ai_vllm_') && c.status === 'running'; });
    if (!comfyui) {
      el.innerHTML = '<span class="badge badge-red">未找到容器</span>';
    } else if (comfyui.status === 'running') {
      el.innerHTML = '<span class="badge badge-green">ComfyUI 运行中</span> <span style="font-size:12px;color:var(--text-dim);margin-left:8px">可直接打开界面</span>';
      actionsDiv.style.display = 'flex';
    } else {
      el.innerHTML = '<span class="badge badge-red">ComfyUI 未启动 (' + comfyui.status + ')</span>';
      // Show prompt only if vLLM is running (needs switching)
      var vllmRunning = vllm && vllm.status === 'running';
      if (vllmRunning) {
        promptDiv.style.display = 'block';
        promptDiv.querySelector('#comfyui-prompt-msg').innerHTML =
          '⚠️ vLLM 正在运行（VRAM 独占），系统会先停止 vLLM 再启动 ComfyUI，预计约 90 秒。';
      } else {
        // No conflict, just need to start ComfyUI
        promptDiv.style.display = 'block';
        promptDiv.querySelector('#comfyui-prompt-msg').innerHTML =
          'vLLM 未运行，启动 ComfyUI 无需切换，预计约 60 秒。';
      }
    }
  } catch(e) {
    el.innerHTML = '<span class="badge badge-yellow">状态检测失败</span>';
  }
}
checkComfyUI();

var _comfyUIAutoStarted = false;
async function autoStartComfyUI() {
  if (_comfyUIAutoStarted) return;
  _comfyUIAutoStarted = true;
  var promptDiv = document.getElementById('comfyui-prompt');
  var progressDiv = document.getElementById('comfyui-progress');
  var progressText = document.getElementById('comfyui-progress-text');
  var progressBar = document.getElementById('comfyui-progress-bar');
  var promptBtns = document.getElementById('comfyui-prompt-btns');

  // Hide buttons, show progress
  promptBtns.style.display = 'none';
  progressDiv.style.display = 'block';
  progressText.textContent = '正在停止 vLLM…';
  progressBar.style.width = '10%';
  progressBar.style.background = 'var(--warn)';

  // Stop any running vLLM container if active
  try {
    // Find active vLLM container from status
    var sr = await fetch('/status');
    var sd = await sr.json();
    var activeVllm = (sd.containers || []).find(function(c) { return c.name.startsWith('ai_vllm_') && c.status === 'running'; });
    if (activeVllm) {
      var r = await fetch('/api/container/stop/' + activeVllm.name, {method:'POST'});
      var d = await r.json();
      if (d.error) { progressText.textContent = '停止 vLLM 失败: ' + d.error; return; }
    }
  } catch(e) {
    progressText.textContent = '请求失败: ' + e.message; return;
  }

  // Short wait for vLLM to release VRAM
  progressBar.style.width = '30%';
  progressText.textContent = '等待 GPU 释放…';
  await new Promise(function(res){ setTimeout(res, 3000); });

  // Start ComfyUI
  progressBar.style.width = '40%';
  progressText.textContent = '正在启动 ComfyUI 容器…';
  try {
    var r = await fetch('/api/container/start/ai_comfyui', {method:'POST'});
    var d = await r.json();
    if (d.error) { progressText.textContent = '启动 ComfyUI 失败: ' + d.error; return; }
  } catch(e) {
    progressText.textContent = '请求失败: ' + e.message; return;
  }

  // Poll until ComfyUI is reachable (~60s)
  progressBar.style.width = '50%';
  progressBar.style.background = 'var(--accent)';
  var elapsed = 0;
  var maxWait = 120;
  await new Promise(function(resolve, reject) {
    var poll = setInterval(async function() {
      elapsed += 3;
      var pct = Math.min(50 + Math.round((elapsed / maxWait) * 50), 98);
      progressBar.style.width = pct + '%';
      progressText.textContent = 'ComfyUI 加载中… ' + elapsed + ' 秒';
      try {
        var r = await fetch('http://192.168.0.19:8188', {method:'HEAD', mode:'no-cors'});
        clearInterval(poll);
        resolve();
      } catch(e) {
        if (elapsed >= maxWait) { clearInterval(poll); reject(new Error('超时')); }
      }
    }, 3000);
  }).catch(function(err) {
    progressText.textContent = '启动成功（' + elapsed + ' 秒），但界面可能还在初始化。您可以稍后尝试打开。';
    progressBar.style.width = '100%';
    progressBar.style.background = 'var(--warn)';
    return;
  });

  progressBar.style.width = '100%';
  progressBar.style.background = '#22c55e';
  progressText.textContent = 'ComfyUI 启动完成！点击下方「打开 ComfyUI 界面」按钮。';

  // Refresh status
  setTimeout(function() {
    document.getElementById('comfyui-actions-default').style.display = 'flex';
    progressDiv.style.display = 'none';
    promptDiv.style.display = 'none';
    actionsDiv.style.display = 'flex';
    document.getElementById('comfyui-status').innerHTML =
      '<span class="badge badge-green">ComfyUI 运行中</span> <span style="font-size:12px;color:var(--text-dim);margin-left:8px">可直接打开界面</span>';
  }, 2000);
}

function cancelComfyUIPrompt() {
  document.getElementById('comfyui-prompt').style.display = 'none';
  document.getElementById('comfyui-actions-default').style.display = 'flex';
}

// ── ComfyUI Workflow Browser ──
var _categoryLabels = {image: '图像生成', video: '视频生成', digital_human: '数字人'};

async function loadWorkflowBrowser() {
  var browser = document.getElementById('workflow-browser');
  try {
    var [wfRes, msRes] = await Promise.all([
      fetch('/api/comfyui/workflows'),
      fetch('/api/comfyui/model-status')
    ]);
    if (!wfRes.ok || !msRes.ok) throw new Error('API error');
    var wfData = await wfRes.json();
    var msData = await msRes.json();
    var workflows = wfData.workflows || [];
    var wfStatus = msData.workflows || {};

    if (workflows.length === 0) {
      browser.innerHTML = '<div style="color:var(--text-dim);font-size:13px">未找到内置工作流</div>';
      return;
    }

    // Group by category
    var groups = {};
    for (var i = 0; i < workflows.length; i++) {
      var wf = workflows[i];
      var cat = wf.category || 'other';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(wf);
    }

    var html = '';
    var catOrder = ['image', 'video', 'digital_human', 'other'];
    for (var ci = 0; ci < catOrder.length; ci++) {
      var cat = catOrder[ci];
      var items = groups[cat];
      if (!items || items.length === 0) continue;
      var catLabel = _categoryLabels[cat] || cat;
      html += '<div>';
      html += '<h3 style="font-size:14px;color:var(--text-dim);margin-bottom:10px;border-bottom:1px solid var(--border);padding-bottom:6px">' + catLabel + '</h3>';
      html += '<div style="display:flex;flex-direction:column;gap:10px">';
      for (var j = 0; j < items.length; j++) {
        var w = items[j];
        var mg = w.model_group;
        var ready = mg && wfStatus[mg] ? wfStatus[mg].ready : false;
        var statusBadge = mg
          ? (ready
            ? '<span class="badge badge-green" style="font-size:11px">模型就绪</span>'
            : '<span class="badge badge-yellow" style="font-size:11px">需下载模型</span>')
          : '';
        html += '<div style="display:flex;align-items:flex-start;gap:12px;padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:8px">';
        html += '<span style="font-size:24px">' + w.icon + '</span>';
        html += '<div style="flex:1;min-width:0">';
        html += '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">';
        html += '<span style="font-weight:600">' + w.name + '</span>';
        html += statusBadge;
        html += '</div>';
        html += '<div style="font-size:13px;color:var(--text-dim);margin-bottom:8px">' + w.description + '</div>';
        html += '<div style="display:flex;gap:8px;flex-wrap:wrap">';
        html += '<a href="/api/comfyui/workflows/' + w.filename + '" download class="btn btn-ghost" style="font-size:12px;padding:4px 10px">下载 JSON</a>';
        html += '</div>';
        html += '</div></div>';
      }
      html += '</div></div>';
    }
    browser.innerHTML = html;

    // HDD config banner
    var card = document.getElementById('comfyui-model-paths-card');
    var content = document.getElementById('comfyui-model-paths-content');
    if (card && content) {
      if (msData.hdd_set) {
        card.style.display = 'block';
        content.innerHTML = '<p style="font-size:13px;color:var(--green);margin-bottom:8px">\u2705 HDD \u6a21\u578b\u8def\u5f84\u5df2\u914d\u7f6e: <code>' + msData.hdd_path + '</code></p>'
          + '<p style="font-size:13px;color:var(--text-dim)">\u5927\u578b\u6a21\u578b\uff08\u5982 CogVideoX\uff09\u53ef\u653e\u5728\u6b64\u76ee\u5f55\uff0cComfyUI \u4f1a\u81ea\u52a8\u626b\u63cf\u3002</p>';
      } else {
        card.style.display = 'block';
        content.innerHTML = '<div style="padding:16px;background:var(--bg);border:1px solid var(--warn);border-radius:8px">'
          + '<p style="font-size:14px;margin-bottom:8px">\u26a0\ufe0f \u5c1a\u672a\u914d\u7f6e HDD \u6a21\u578b\u8def\u5f84</p>'
          + '<p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">\u5927\u6a21\u578b\uff08\u5982 CogVideoX ~13 GB\uff09\u5efa\u8bae\u5b58\u653e\u5728 HDD \u4e2d\u3002\u8bf7\u5728 <code>.env</code> \u6587\u4ef6\u4e2d\u8bbe\u7f6e\uff1a</p>'
          + '<code style="font-size:12px;display:block;padding:8px;background:var(--bg);border-radius:4px">COMFYUI_MODELS_HDD=/mnt/hdd/comfyui-models</code>'
          + '<p style="font-size:12px;color:var(--text-dim);margin-top:8px">设置后需重启 Docker 栈: <code>cd ~/' + APP_NAME + ' &amp;&amp; docker compose up -d</code></p>'
          + '</div>';
      }
    }
  } catch(e) {
    browser.innerHTML = '<div style="color:var(--warn);font-size:13px">\u52a0\u8f7d\u5de5\u4f5c\u6d41\u5217\u8868\u5931\u8d25: ' + e.message + '</div>';
    console.warn('Failed to load workflow browser:', e);
  }
}
loadWorkflowBrowser();
</script>
"""
    return page("视觉生成", "/comfyui", body)


# ── /gpu ─────────────────────────────────────────────────────────────────────
@app.get("/gpu", response_class=HTMLResponse)
async def gpu_page():
    body = """
<div id="dependency-alert" style="display:none;"></div>

<div class="card">
  <h2>GPU 状态</h2>
  <div class="gpu-grid" style="grid-template-columns:repeat(4,1fr)">
    <div class="gpu-stat"><div class="val" id="vram-used">—</div><div class="lbl">显存已用</div></div>
    <div class="gpu-stat"><div class="val" id="vram-free">—</div><div class="lbl">显存剩余</div></div>
    <div class="gpu-stat"><div class="val" id="gpu-util">—</div><div class="lbl">核心利用率</div></div>
    <div class="gpu-stat"><div class="val" id="gpu-temp">—</div><div class="lbl">GPU 温度</div></div>
  </div>
  <div class="vram-bar-wrap"><div class="vram-bar" id="vram-bar" style="width:0%"></div></div>
  <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text-dim);margin-top:6px">
    <span id="gpu-name">—</span>
    <span>功耗 <span id="gpu-power">—</span> &nbsp;·&nbsp; 每 10s 刷新</span>
  </div>
</div>

<div class="card">
  <h2>GPU 进程</h2>
  <div id="gpu-procs"><div style="color:var(--text-dim);font-size:13px">加载中…</div></div>
</div>

<div class="card">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
    <h2 style="margin-bottom:0">容器状态</h2>
    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:0">
      <span style="font-size:12px;color:var(--text-dim)">手动控制</span>
      <div class="toggle-wrap">
        <input type="checkbox" id="ctrl-toggle" onchange="onToggleChange()">
        <span class="toggle-track"><span class="toggle-thumb"></span></span>
      </div>
    </label>
  </div>
  <div id="ctrl-hint" style="font-size:12px;color:var(--text-dim);margin-bottom:14px;display:none">
    ⚠️ vLLM 和 ComfyUI 不能同时运行，启动前请先停止另一个。
  </div>
  <div id="container-list"><div style="color:var(--text-dim);font-size:13px">加载中…</div></div>
</div>

<div class="card" id="cookie-card" style="display:none;">
  <h2>YouTube Cookie 状态</h2>
  <div id="cookie-content"><div style="color:var(--text-dim);font-size:13px">加载中…</div></div>
</div>
<style>
.ck-spin { display:inline-block; animation: ck-rotate 1s linear infinite; }
@keyframes ck-rotate { from { transform:rotate(0deg); } to { transform:rotate(360deg); } }
</style>

<style>
.toggle-wrap { position:relative; display:inline-block; width:36px; height:20px; }
.toggle-wrap input { opacity:0; width:0; height:0; position:absolute; }
.toggle-track {
  position:absolute; inset:0; border-radius:20px;
  background:var(--border); cursor:pointer; transition:background 0.2s;
}
.toggle-wrap input:checked + .toggle-track { background:var(--accent); }
.toggle-thumb {
  position:absolute; top:3px; left:3px; width:14px; height:14px;
  border-radius:50%; background:#fff; transition:transform 0.2s;
}
.toggle-wrap input:checked + .toggle-track .toggle-thumb { transform:translateX(16px); }

.proc-row {
  display:flex; align-items:center; gap:10px;
  padding:8px 0; border-bottom:1px solid var(--border);
  font-size:13px;
}
.proc-row:last-child { border-bottom:none; }
.proc-row .pname { flex:1; font-family:monospace; }
.proc-row .pmem  { color:var(--accent); font-weight:600; min-width:70px; text-align:right; }

.cstat {
  display:flex; align-items:center; gap:10px;
  padding:10px 0; border-bottom:1px solid var(--border);
}
.cstat:last-child { border-bottom:none; }
.cstat .cname { flex:1; font-family:monospace; font-size:13px; }
.cstat .cmeta { font-size:12px; color:var(--text-dim); min-width:160px; text-align:right; }
.cstat .cbtns { display:flex; gap:6px; flex-shrink:0; }
</style>

<script>
var manualMode = false;

function onToggleChange() {
  manualMode = document.getElementById('ctrl-toggle').checked;
  document.getElementById('ctrl-hint').style.display = manualMode ? 'block' : 'none';
  renderContainers(window._lastContainers || []);
}

function renderGpuProcs(procs) {
  var el = document.getElementById('gpu-procs');
  if (!procs || !procs.length) {
    el.innerHTML = '<div style="color:var(--text-dim);font-size:13px">无 GPU 进程</div>';
    return;
  }
  var html = '';
  for (var i = 0; i < procs.length; i++) {
    var p = procs[i];
    var mb = p.mem_mb;
    var memStr = mb >= 1024 ? (mb/1024).toFixed(1) + ' GB' : mb + ' MB';
    html += '<div class="proc-row">'
          + '<span class="badge badge-blue">PID ' + p.pid + '</span>'
          + '<span class="pname">' + p.name + '</span>'
          + '<span class="pmem">' + memStr + '</span>'
          + '</div>';
  }
  el.innerHTML = html;
}

function renderContainers(containers) {
  window._lastContainers = containers;
  var el = document.getElementById('container-list');
  if (!containers || !containers.length) {
    el.innerHTML = '<div style="color:var(--text-dim);font-size:13px">无法获取容器信息</div>';
    return;
  }
  var html = '';
  for (var i = 0; i < containers.length; i++) {
    var c = containers[i];
    var running = (c.status === 'running');
    var badge = running
      ? '<span class="badge badge-green">运行中</span>'
      : '<span class="badge badge-red">' + c.status + '</span>';

    var meta = '';
    if (running && c.cpu_pct !== null && c.cpu_pct !== undefined) {
      var memStr = '';
      if (c.mem_mb !== null && c.mem_mb !== undefined) {
        memStr = c.mem_mb >= 1024
          ? ' &nbsp;·&nbsp; 内存 ' + (c.mem_mb/1024).toFixed(1) + ' GB'
          : ' &nbsp;·&nbsp; 内存 ' + c.mem_mb + ' MB';
      }
      meta = '<span class="cmeta">CPU ' + c.cpu_pct + '%' + memStr + '</span>';
    }

    var btns = '';
    if (manualMode) {
      var action = running ? 'stop' : 'start';
      var cls = running ? 'btn btn-danger' : 'btn btn-primary';
      var lbl = running ? '停止' : '启动';
      btns = '<button class="' + cls + '" style="font-size:12px;padding:5px 12px" data-action="' + action + '" data-name="' + c.name + '">' + lbl + '</button>';
    }
    html += '<div class="cstat"><span class="cname">' + c.name + '</span>' + badge + meta + '<div class="cbtns">' + btns + '</div></div>';
  }
  el.innerHTML = html;
  el.querySelectorAll('button[data-action]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      ctrlContainer(this.getAttribute('data-action'), this.getAttribute('data-name'));
    });
  });
}

function updateGpuExtras(d) {
  var el = document.getElementById('gpu-name');
  if (el && d.gpu_name) el.textContent = d.gpu_name + (d.driver_version ? '  (Driver ' + d.driver_version + ')' : '');
}

async function loadContainers() {
  // Phase 1: render container list immediately via lite endpoint (~50ms)
  try {
    var lr = await fetch('/api/gpu-status-lite');
    if (lr.ok) {
      var ld = await lr.json();
      if (ld.containers && ld.containers.length) {
        renderContainers(ld.containers);
      }
    }
  } catch(e) { /* lite failed, fall through to full status */ }

  // Phase 2: full status (GPU stats, CPU %, etc.) — takes ~1-2s
  try {
    var r = await fetch('/status');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    var d = await r.json();
    updateGpuWidget(d);
    updateGpuExtras(d);
    renderGpuProcs(d.gpu_processes || []);
    renderContainers(d.containers || []);
  } catch(e) {
    // Only show error if lite also failed (container-list is empty)
    if (!window._lastContainers || !window._lastContainers.length) {
      document.getElementById('container-list').innerHTML =
        '<div style="color:var(--danger);font-size:13px">加载失败: ' + e.message + '</div>';
    }
    document.getElementById('gpu-procs').innerHTML =
      '<div style="color:var(--text-dim);font-size:13px">GPU 状态加载中…</div>';
  }
}

async function ctrlContainer(action, name) {
  // Build smart confirmation message based on VRAM conflict rules
  var containers = window._lastContainers || [];
  var lines = [];
  var estSec = 0;
  var toStopForBanner = [];

  if (action === 'start') {
    // VRAM conflict: any vllm <-> comfyui are mutually exclusive
    // Also vllm containers conflict with each other (only one can run)
    var mustStop = [];
    var isVllm = name.startsWith('ai_vllm_');
    if (isVllm) {
      // Starting a vllm: stop comfyui AND any other running vllm
      mustStop = containers.filter(function(c) {
        return c.status === 'running' && c.name !== name &&
               (c.name === 'ai_comfyui' || c.name.startsWith('ai_vllm_'));
      }).map(function(c) { return c.name; });
    } else if (name === 'ai_comfyui') {
      // Starting comfyui: stop all vllm containers
      mustStop = containers.filter(function(c) {
        return c.status === 'running' && c.name.startsWith('ai_vllm_');
      }).map(function(c) { return c.name; });
    }
    toStopForBanner = mustStop;

    if (mustStop.length) {
      lines.push('需要先停止以下容器（VRAM 冲突）：');
      mustStop.forEach(function(cn) { lines.push('  ⛔ ' + cn); });
      estSec += mustStop.length * 20;
      lines.push('');
    }
    lines.push('然后启动：  ✅ ' + name);

    // Estimated startup time
    var estStart = name.startsWith('ai_vllm_') ? 120 : (name === 'ai_comfyui' ? 60 : 15);
    estSec += estStart;

    if (name.startsWith('ai_vllm_')) {
      lines.push('');
      lines.push('预计时间：约 ' + Math.round(estSec/60) + ' 分钟（模型加载）');
    } else {
      lines.push('');
      lines.push('预计时间：约 ' + estSec + ' 秒');
    }
  } else {
    estSec = 20;
    lines.push('将停止：  ⛔ ' + name);
    lines.push('');
    lines.push('预计时间：约 15-20 秒');
  }

  if (!confirm(lines.join('\\n') + '\\n\\n确认执行？')) return;

  // ── Show switching banner immediately after user confirms ──────────────
  var bannerTitle, bannerDetail, bannerTarget;
  if (action === 'start') {
    var stopStr = toStopForBanner.length ? '先停止 ' + toStopForBanner.join(', ') + ' → ' : '';
    bannerTitle = '正在启动 ' + name;
    bannerDetail = stopStr + '启动 ' + name + (name.startsWith('ai_vllm_') ? '（需加载模型，约 1-2 分钟）' : '（约 ' + estSec + ' 秒）');
    bannerTarget = name; // poll for this container to become "running"
  } else {
    bannerTitle = '正在停止 ' + name;
    bannerDetail = '停止 ' + name + '，约 15-20 秒';
    bannerTarget = null; // stop has no "running" target to poll
  }
  if (typeof showSwitchBanner === 'function') {
    showSwitchBanner({
      title: bannerTitle,
      detail: bannerDetail,
      estimateSec: estSec,
      stopContainers: toStopForBanner,
      startContainer: bannerTarget,
    });
  }

  // If starting with conflicts, stop conflicting containers first
  if (action === 'start') {
    var isVllm2 = name.startsWith('ai_vllm_');
    var toStop = [];
    if (isVllm2) {
      toStop = containers.filter(function(c) {
        return c.status === 'running' && c.name !== name &&
               (c.name === 'ai_comfyui' || c.name.startsWith('ai_vllm_'));
      }).map(function(c) { return c.name; });
    } else if (name === 'ai_comfyui') {
      toStop = containers.filter(function(c) {
        return c.status === 'running' && c.name.startsWith('ai_vllm_');
      }).map(function(c) { return c.name; });
    }
    for (var i = 0; i < toStop.length; i++) {
      try {
        await fetch('/api/container/stop/' + toStop[i], {method:'POST'});
      } catch(e) {}
      await new Promise(function(r){ setTimeout(r, 3000); });
    }
  }

  try {
    var r = await fetch('/api/container/' + action + '/' + name, {method:'POST'});
    var d = await r.json();
    if (d.error) {
      if (typeof _completeSwitchBanner === 'function') _completeSwitchBanner(false, '操作失败: ' + d.error);
      else alert('操作失败: ' + d.error);
    } else if (action === 'stop') {
      // Stop completes quickly — mark done after a short delay
      setTimeout(function() {
        if (typeof _completeSwitchBanner === 'function') _completeSwitchBanner(true, name + ' 已停止 ✅');
      }, 3000);
    }
    // For 'start', banner polls _pollSwitchStatus every 4s until container is running
  } catch(e) {
    if (typeof _completeSwitchBanner === 'function') _completeSwitchBanner(false, '请求失败: ' + e.message);
    else alert('请求失败: ' + e.message);
  }
  setTimeout(loadContainers, 3000);
}

loadContainers();
setInterval(loadContainers, 10000);

// ── Cookie status card ──────────────────────────────────────────────────────
function _fmtAge(hours) {
  if (hours === null || hours === undefined) return '未知';
  var totalMin = Math.round(hours * 60);
  if (totalMin < 1) return '刚刚';
  if (totalMin < 60) return totalMin + ' 分钟前';
  var h = Math.floor(totalMin / 60);
  var m = totalMin % 60;
  return m > 0 ? h + ' 小时 ' + m + ' 分钟前' : h + ' 小时前';
}

function loadCookieStatus() {
  fetch('/api/cookie-status').then(r => r.json()).then(d => {
    const card = document.getElementById('cookie-card');
    const ct = document.getElementById('cookie-content');
    if (!card || !ct) return;
    if (!d.enabled) { card.style.display = 'none'; return; }
    card.style.display = 'block';

    var isRefreshing = d.manager && d.manager.is_refreshing;
    let html = '<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center">';

    // Refreshing spinner
    if (isRefreshing) {
      html += '<span class="badge" style="font-size:14px;background:rgba(59,130,246,0.15);color:#3b82f6">'
        + '<span class="ck-spin">⟳</span> 正在刷新 Cookies…</span>';
    } else if (!d.file_exists) {
      html += '<span class="badge badge-red" style="font-size:14px">❌ Cookie 文件不存在</span>';
    } else if (d.cookie_age_hours <= 12) {
      html += '<span class="badge badge-green" style="font-size:14px">✅ 正常</span>';
      html += '<span style="color:var(--text-dim);font-size:13px">' + _fmtAge(d.cookie_age_hours) + '刷新</span>';
    } else if (d.cookie_age_hours <= 24) {
      html += '<span class="badge" style="font-size:14px;background:rgba(245,158,11,0.15);color:#f59e0b">⚠️ 即将过期</span>';
      html += '<span style="color:var(--text-dim);font-size:13px">' + _fmtAge(d.cookie_age_hours) + '刷新</span>';
    } else {
      html += '<span class="badge badge-red" style="font-size:14px">❌ 可能已过期</span>';
      html += '<span style="color:var(--text-dim);font-size:13px">' + _fmtAge(d.cookie_age_hours) + '刷新</span>';
    }

    // Cookie Manager status
    if (d.manager) {
      html += '<span style="color:var(--text-dim);font-size:13px">· Manager: ✅ 运行中';
      if (d.manager.refresh_count > 0) html += ' · 已刷新 ' + d.manager.refresh_count + ' 次';
      html += '</span>';
    } else {
      html += '<span style="color:#f59e0b;font-size:13px">· Manager: ⏸ 未运行</span>';
    }

    html += '</div>';

    // Action links
    const vnc = 'http://' + location.hostname + ':6901/vnc.html';
    html += '<div style="margin-top:10px;font-size:13px">';
    html += '<a href="' + vnc + '" target="_blank" style="color:var(--accent);margin-right:16px">🖥 打开 noVNC 登录 YouTube</a>';
    if (isRefreshing) {
      html += '<span style="color:var(--text-dim)"><span class="ck-spin">⟳</span> 刷新中…</span>';
    } else {
      html += '<a href="#" onclick="refreshCookies();return false;" style="color:var(--accent)">🔄 手动刷新 Cookies</a>';
    }
    html += '</div>';

    ct.innerHTML = html;

    // While refreshing, poll faster (every 3s)
    if (isRefreshing && !window._ckFastPoll) {
      window._ckFastPoll = setInterval(loadCookieStatus, 3000);
    } else if (!isRefreshing && window._ckFastPoll) {
      clearInterval(window._ckFastPoll);
      window._ckFastPoll = null;
    }
  }).catch(() => {});
}

async function refreshCookies() {
  try {
    // Fire-and-forget — don't wait for the full refresh (can take 30s+)
    fetch('/api/cookie-refresh', {method:'POST'});
    // Immediately start fast polling to show spinner
    loadCookieStatus();
  } catch(e) { alert('请求失败: ' + e.message); }
}

loadCookieStatus();
setInterval(loadCookieStatus, 30000);
</script>
"""
    return page("GPU 控制", "/gpu", body)


@app.post("/api/container/{action}/{name}")
async def container_action(action: str, name: str):
    if name not in GPU_MANAGED_CONTAINERS:
        return JSONResponse({"error": f"容器 {name} 不在允许列表中"}, status_code=403)
    if action not in ("start", "stop"):
        return JSONResponse({"error": "action 必须是 start 或 stop"}, status_code=400)
    try:
        dc = docker.from_env()
        try:
            c = dc.containers.get(name)
        except docker.errors.NotFound:
            # Container doesn't exist — create it via docker compose
            # Use subprocess for compose to handle profiles correctly
            import subprocess as _subp
            _subp.run(["docker", "compose", "create", name], capture_output=True, timeout=60)
            c = dc.containers.get(name)

        if action == "start":
            c.start()
        else:
            c.stop(timeout=15)
        return JSONResponse({"ok": True})
    except docker.errors.NotFound:
        return JSONResponse({"error": f"容器 {name} 无法创建"})
    except Exception as e:
        return JSONResponse({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# /models — Model Manager
# ──────────────────────────────────────────────────────────────────────────────
# Low-coupling design: this block only depends on MODELS_ROOT, VLLM_CONTAINER,
# HF_TOKEN (env vars) and the docker + huggingface_hub libraries.
# To reuse in another project: copy this block + update the three env vars above.
# ══════════════════════════════════════════════════════════════════════════════

def _scan_models(root: str) -> list[dict]:
    """Scan MODELS_ROOT for top-level subdirectories that look like HF model dirs."""
    result = []
    root_path = Path(root)
    if not root_path.exists():
        return result
    for entry in sorted(root_path.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        # Determine size
        size_bytes = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
        size_gb = round(size_bytes / (1024 ** 3), 2)
        # Detect if it's a HuggingFace model (has config.json)
        is_hf = (entry / "config.json").exists()
        # Check if this is the currently loaded vLLM model
        result.append({
            "name": entry.name,
            "path": str(entry),
            "size_gb": size_gb,
            "is_hf": is_hf,
        })
    return result


def _run_download(task_id: str, repo_id: str, local_dir: str, hf_token: Optional[str]):
    """Background thread: download HuggingFace model with detailed progress tracking."""
    task = _download_tasks[task_id]
    try:
        from huggingface_hub import snapshot_download, HfApi

        # Step 1: Get file list + total size from HuggingFace API
        task["log"].append(f"Fetching file list for {repo_id}...")
        api = HfApi()
        try:
            model_info = api.model_info(repo_id, files_metadata=True, token=hf_token or None)
            siblings = model_info.siblings or []
            # Filter out files matching ignore_patterns
            ignore_suffixes = (".md", ".txt")
            ignore_prefixes = ("original/",)
            filtered = [
                s for s in siblings
                if not any(s.rfilename.endswith(suf) for suf in ignore_suffixes)
                and not any(s.rfilename.startswith(pre) for pre in ignore_prefixes)
            ]
            total_bytes = sum(getattr(s, "size", 0) or 0 for s in filtered)
            total_files = len(filtered)
            file_list = [
                {"name": s.rfilename, "size": getattr(s, "size", 0) or 0}
                for s in filtered
            ]
        except Exception:
            # If we can't get file info, proceed with unknown totals
            total_bytes = 0
            total_files = 0
            file_list = []

        task["progress"] = {
            "total_files": total_files,
            "completed_files": 0,
            "total_bytes": total_bytes,
            "downloaded_bytes": 0,
            "current_file": None,
            "last_update": time.time(),
            "stall_warning": False,
            "file_list": file_list[:50],  # send first 50 files for display
        }
        task["log"].append(
            f"Found {total_files} files ({_fmt_bytes(total_bytes)} total)"
        )
        task["log"].append(f"Downloading to {local_dir}...")
        task["log"].append(f"Source: https://huggingface.co/{repo_id}")

        # Step 2: Start directory size monitor thread for byte-level progress
        monitor = threading.Thread(
            target=_monitor_download_dir,
            args=(task_id, local_dir),
            daemon=True,
        )
        monitor.start()

        # Step 3: Create tqdm factory that injects task reference
        def make_progress(*args, **kwargs):
            kwargs["_task"] = task
            return _ProgressTracker(*args, **kwargs)

        # Step 4: Download with progress tracking
        kwargs = {
            "repo_id": repo_id,
            "local_dir": local_dir,
            "ignore_patterns": ["*.md", "*.txt", "original/*"],
            "tqdm_class": make_progress,
        }
        if hf_token:
            kwargs["token"] = hf_token
        snapshot_download(**kwargs)

        task["status"] = "done"
        task["progress"]["downloaded_bytes"] = task["progress"]["total_bytes"]
        task["progress"]["completed_files"] = task["progress"]["total_files"]
        task["progress"]["current_file"] = None
        task["log"].append(f"Download complete: {_fmt_bytes(total_bytes)}")
    except Exception as e:
        task["status"] = "error"
        task["log"].append(f"Download failed: {e}")


def _stall_checker():
    """Background daemon thread: check for stalled downloads (no progress for 120s)."""
    while True:
        time.sleep(30)
        for tid, task in list(_download_tasks.items()):
            if task["status"] != "running":
                continue
            prog = task.get("progress")
            if not prog:
                continue
            last = prog.get("last_update", 0)
            if last > 0 and (time.time() - last) > 120:
                prog["stall_warning"] = True
                if "stall reported" not in str(task["log"][-1:]):
                    task["log"].append(
                        "Warning: no download progress for 120+ seconds — connection may be stalled"
                    )


# Start stall checker daemon
threading.Thread(target=_stall_checker, daemon=True).start()


@app.get("/models", response_class=HTMLResponse)
async def models_page():
    body = """
<div id="dependency-alert" style="display:none;"></div>

<style>
.hf-search-bar { display:flex; gap:8px; flex-wrap:wrap; align-items:flex-end; margin-bottom:12px; }
.hf-search-bar input[type="text"] { flex:1; min-width:200px; }
.hf-filters { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; }
.hf-filters select { min-width:120px; }
.hf-results { display:flex; flex-direction:column; gap:8px; }
.hf-card { display:flex; align-items:center; gap:12px; padding:12px 16px; border:1px solid rgba(255,255,255,0.08); border-radius:8px; background:rgba(255,255,255,0.02); }
.hf-card:hover { background:rgba(255,255,255,0.04); }
.hf-card-info { flex:1; min-width:0; }
.hf-card-name { font-weight:600; font-family:monospace; font-size:14px; }
.hf-card-name a { color:var(--text-primary); text-decoration:none; }
.hf-card-name a:hover { color:var(--accent); }
.hf-card-meta { font-size:12px; color:var(--text-dim); margin-top:4px; }
.hf-card-actions { flex-shrink:0; display:flex; gap:6px; flex-direction:column; align-items:flex-end; }
.hf-badge { display:inline-block; padding:2px 6px; border-radius:4px; font-size:11px; font-weight:600; margin-right:4px; }
.hf-badge.awq { background:#7c3aed; color:#fff; }
.hf-badge.gptq { background:#2563eb; color:#fff; }
.hf-badge.gguf { background:#dc2626; color:#fff; }
.hf-badge.fp8 { background:#059669; color:#fff; }
.hf-badge.bf16 { background:#d97706; color:#fff; }
.hf-empty { color:var(--text-dim); font-size:13px; padding:20px 0; text-align:center; }
</style>

<div class="card">
  <h2>搜索 HuggingFace 模型</h2>
  <div class="hf-search-bar">
    <input type="text" id="hf-query" placeholder="搜索模型，如 Qwen AWQ、Llama-3、CogVideoX..." style="font-family:monospace">
    <button class="btn btn-primary" onclick="hfSearch()">搜索</button>
    <button class="btn" onclick="hfBrowse()">浏览全部</button>
  </div>
  <div class="hf-filters">
    <select id="hf-type" onchange="hfSearch()">
      <option value="">全部类型</option>
      <option value="text-generation">LLM 文字生成</option>
      <option value="text-to-image">文生图</option>
      <option value="text-to-video">文生视频</option>
      <option value="automatic-speech-recognition">语音识别</option>
    </select>
    <select id="hf-quant" onchange="hfSearch()">
      <option value="">全部量化</option>
      <option value="awq">AWQ</option>
      <option value="gptq">GPTQ</option>
      <option value="gguf">GGUF</option>
    </select>
    <select id="hf-sort" onchange="hfSearch()">
      <option value="downloads">按下载量</option>
      <option value="trending">按热度</option>
      <option value="lastModified">按更新时间</option>
    </select>
  </div>
  <div id="hf-results-area"><div class="hf-empty">输入关键字搜索，或点击"浏览全部"查看热门模型</div></div>
</div>

<style>
/* Preset workflows styling */
.preset-workflows { margin-top: 16px; }
.preset-card { margin-bottom: 12px; border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; background: rgba(255,255,255,0.02); overflow: hidden; }
.preset-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.05); }
.preset-header h3 { margin: 0; font-size: 16px; font-weight: 600; }
.preset-badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; margin-left: 8px; }
.preset-badge.ready { background: #059669; color: #fff; }
.preset-badge.missing { background: #dc2626; color: #fff; }
.preset-body { padding: 12px 16px; }
.preset-model-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.preset-model-item { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
.preset-model-name { font-family: monospace; }
.preset-model-status { font-size: 12px; color: var(--text-dim); }
.preset-model-status.ok { color: #059669; }
.preset-model-status.missing { color: #dc2626; }
.preset-actions { padding: 12px 16px; background: rgba(255,255,255,0.02); border-top: 1px solid rgba(255,255,255,0.05); display: flex; gap: 12px; align-items: center; }
.preset-desc { font-size: 13px; color: var(--text-dim); margin-right: auto; }
.preset-size { font-size: 12px; color: var(--text-dim); margin-left: 8px; }
</style>

<div class="card preset-workflows">
  <h2>预置工作流模型</h2>
  <p style="font-size:13px;color:var(--text-dim);margin-bottom:16px">
    一键下载 ComfyUI 预置工作流所需的全部模型文件。建议按工作流逐个下载。
    <br>首次使用请先下载所需模型，然后停止 vLLM 并手动启动 ComfyUI 容器。
  </p>
  <div id="preset-workflows"><div style="color:var(--text-dim);font-size:13px">加载中…</div></div>
</div>

<script>
async function loadPresetStatus() {
  const r = await fetch('/api/comfyui/model-status');
  const d = await r.json();
  const container = document.getElementById('preset-workflows');

  if (!d.workflows || Object.keys(d.workflows).length === 0) {
    container.innerHTML = '<div class="preset-empty" style="color:var(--text-dim);font-size:13px;padding:12px">无预置工作流配置</div>';
    return;
  }

  container.innerHTML = Object.values(d.workflows).map(function(wf) {
    const readyBadge = wf.ready
      ? '<span class="preset-badge ready">✓ 就绪</span>'
      : '<span class="preset-badge missing">缺失部分模型</span>';

    // Build model detail rows
    const modelRows = wf.models.map(function(mKey) {
      const m = d.models[mKey];
      if (!m) return '';
      const statusClass = m.ready ? 'ok' : 'missing';
      const statusText = m.ready ? '✓ 已存在' : '✗ 缺失 ' + m.missing_files.length + ' 个文件';
      const sizeInfo = m.size_gb > 0 ? `<span class="preset-size">(~${m.size_gb} GB)</span>` : '';
      const missingList = m.missing_files.length > 0
        ? '<div style="font-size:11px;color:#dc2626;margin-top:4px;font-family:monospace">' + m.missing_files.map(f => f.replace(/^.*comfyui\\//, '')).join('<br>') + '</div>'
        : '';
      return `
        <div class="preset-model-item">
          <div>
            <span class="preset-model-name">${m.label}</span>
            ${sizeInfo}
            <div class="preset-model-status ${statusClass}">${statusText}</div>
            ${missingList}
          </div>
          <div></div>
        </div>
      `;
    }).join('');

    return `
      <div class="preset-card" id="preset-${wf.label.replace(/\\s+/g, '-').toLowerCase()}">
        <div class="preset-header">
          <h3>${wf.label} ${readyBadge}</h3>
          <div style="font-size:12px;color:var(--text-dim)">
            总大小: ${wf.total_size.toFixed(1)} GB
          </div>
        </div>
        <div class="preset-body">
          <div class="preset-model-list">
            ${modelRows}
          </div>
        </div>
        <div class="preset-actions">
          <span class="preset-desc">
            提示: 下载完成后，请停止 vLLM 容器，然后使用 <code>docker compose --profile comfyui up -d</code> 启动 ComfyUI。
          </span>
          <button class="btn btn-primary" style="font-size:12px" onclick="downloadPreset('${Object.keys(d.workflows).find(k => d.workflows[k].label === wf.label)}')" ${wf.ready ? 'disabled' : ''}>
            下载全部模型
          </button>
        </div>
      </div>
    `;
  }).join('');

  window._presetModelsData = d;
}

// Dependency alert (same as home page)
function showDependencyAlert(deps) {
  const el = document.getElementById('dependency-alert');
  if (!el || !deps) return;

  let html = '<div class="card" style="margin-bottom:16px;border:1px solid #dc2626;background:rgba(220,38,38,0.08)">';
  html += '<h2 style="margin-top:0;color:#dc2626">⚠️ 系统依赖异常</h2>';
  if (deps.models && (deps.models.issues || deps.models.warnings)) {
    html += '<h3>📦 模型</h3><ul>';
    deps.models.issues.forEach(i => html += `<li style="color:#dc2626">${i}</li>`);
    deps.models.warnings.forEach(w => html += `<li style="color:#d97706">${w}</li>`);
    html += '</ul>';
  }
  if (deps.env && (deps.env.issues || deps.env.warnings)) {
    html += '<h3>📋 配置</h3><ul>';
    deps.env.issues.forEach(i => html += `<li style="color:#dc2626">${i}</li>`);
    deps.env.warnings.forEach(w => html += `<li style="color:#d97706">${w}</li>`);
    html += '</ul>';
  }
  if (deps.data && (deps.data.issues || deps.data.warnings)) {
    html += '<h3>🗄️ 数据目录</h3><ul>';
    deps.data.issues.forEach(i => html += `<li style="color:#dc2626">${i}</li>`);
    deps.data.warnings.forEach(w => html += `<li style="color:#d97706">${w}</li>`);
    html += '</ul>';
  }
  if (deps.docker && deps.docker.issues) {
    html += '<h3>🐳 Docker</h3><ul>';
    deps.docker.issues.forEach(i => html += `<li style="color:#dc2626">${i}</li>`);
    html += '</ul>';
  }
  html += '<p style="font-size:13px;color:var(--text-dim);margin-bottom:0">运行 <code>./paas-controller.sh check-deps</code> 获取详细信息。</p>';
  html += '</div>';
  el.innerHTML = html;
  el.style.display = 'block';
}

// Check dependencies on page load (models page also needs it)
async function checkDepsOnLoad() {
  try {
    const r = await fetch('/status');
    const d = await r.json();
    if (d.dependencies && d.dependencies._overall !== 'ok') {
      showDependencyAlert(d.dependencies);
    }
  } catch(e) {
    // Fail silently
  }
}

// Load preset status on page load

async function downloadPreset(workflowKey) {
  const wf = window._presetModelsData.workflows[workflowKey];
  if (!wf) return alert('未知工作流');

  if (!confirm(`将下载以下缺失模型（共 ${wf.total_size.toFixed(1)} GB）：\\n${wf.label}\\n\\n下载过程可能需要较长时间，期间请不要刷新页面。\\n是否继续？`)) return;

  // Call actual download API
  try {
    const r = await fetch('/api/comfyui/download-preset', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({workflow_key: workflowKey})
    });
    const d = await r.json();
    if (d.error) {
      if (d.already_complete) {
        alert('所有模型已存在，无需下载。');
        loadPresetStatus();
      } else {
        alert('下载失败: ' + d.error);
      }
      return;
    }
    // Show progress inline
    pollPresetDownload(d.task_id, workflowKey);
  } catch (e) {
    alert('请求失败: ' + e.message);
  }
}

function pollPresetDownload(taskId, workflowKey) {
  const cardId = 'preset-' + workflowKey.replace(/_/g, '-');
  const card = document.getElementById(cardId) || document.querySelector('.preset-card');
  let logEl = document.getElementById('preset-dl-log');
  if (!logEl && card) {
    const div = document.createElement('div');
    div.innerHTML = '<div id="preset-dl-log" class="result-box visible" style="font-family:monospace;white-space:pre-wrap;max-height:200px;overflow-y:auto;font-size:12px;margin-top:12px;padding:8px;background:rgba(0,0,0,0.3);border-radius:4px"></div>';
    card.appendChild(div.firstChild);
    logEl = document.getElementById('preset-dl-log');
  }
  const timer = setInterval(async function() {
    try {
      const r = await fetch('/api/comfyui/download-progress/' + taskId);
      const d = await r.json();
      if (logEl) {
        let text = d.log.join('\\n');
        if (d.current_file && d.current_total_bytes > 0) {
          const pct = Math.round((d.current_downloaded_bytes / d.current_total_bytes) * 100);
          const mb = (d.current_downloaded_bytes / (1024*1024)).toFixed(1);
          const totalMb = (d.current_total_bytes / (1024*1024)).toFixed(1);
          text += '\\n  ↳ ' + d.current_file + ': ' + mb + ' / ' + totalMb + ' MB (' + pct + '%)';
        }
        logEl.textContent = text;
        logEl.scrollTop = logEl.scrollHeight;
      }
      if (d.status === 'done' || d.status === 'error') {
        clearInterval(timer);
        loadPresetStatus();  // Refresh model status
      }
    } catch(e) { /* keep polling */ }
  }, 1500);
}

// Load status on page load
window.addEventListener('load', function() {
  checkDepsOnLoad();
});
</script>

<div class="card" id="download-active-card" style="display:none">
  <h2>下载进度</h2>
  <p style="font-size:13px;color:var(--text-dim);margin-bottom:8px">
    模型: <span id="dl-repo-id" style="font-family:monospace"></span>
    <a id="dl-repo-link" href="#" target="_blank" rel="noopener" style="font-size:12px;margin-left:8px;color:var(--accent)">HuggingFace →</a>
  </p>
  <!-- Progress bar -->
  <div id="dl-progress-section" style="display:none">
    <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text-dim);margin-bottom:4px">
      <span id="dl-progress-text">0 / 0 files</span>
      <span id="dl-progress-pct">0%</span>
    </div>
    <div style="width:100%;height:8px;background:rgba(255,255,255,0.08);border-radius:4px;overflow:hidden;margin-bottom:8px">
      <div id="dl-progress-bar" style="width:0%;height:100%;background:var(--accent);border-radius:4px;transition:width 0.5s ease"></div>
    </div>
    <div style="display:flex;gap:16px;font-size:12px;color:var(--text-dim);margin-bottom:8px;flex-wrap:wrap">
      <span>📁 <span id="dl-current-file" style="font-family:monospace">—</span></span>
      <span>⬇ <span id="dl-speed">—</span></span>
      <span>⏱ <span id="dl-eta">—</span></span>
      <span>💾 <span id="dl-bytes">0 B / 0 B</span></span>
    </div>
    <div id="dl-stall-warning" style="display:none;padding:6px 10px;background:#dc2626;color:#fff;border-radius:4px;font-size:12px;margin-bottom:8px">
      ⚠ No download progress for 120+ seconds — connection may be stalled
    </div>
  </div>
  <div class="result-box visible" id="dl-log" style="font-family:monospace;white-space:pre-wrap;max-height:200px;overflow-y:auto;font-size:12px"></div>
</div>

<div class="card">
  <h2>已下载模型</h2>
  <div id="model-list"><div style="color:var(--text-dim);font-size:13px">加载中...</div></div>
</div>

<script>
let _pollTimer = null;
let _activeDlTaskId = null;
let _currentSearchQ = '';

// ── HuggingFace Search ────────────────────────────────────────────────────

function _showResults(msg) {
  document.getElementById('hf-results-area').innerHTML = '<div class="hf-empty">' + msg + '</div>';
}

async function hfSearch() {
  const q = document.getElementById('hf-query').value.trim();
  if (!q) { _showResults('请输入搜索关键字'); return; }
  _currentSearchQ = q;
  const modelType = document.getElementById('hf-type').value;
  const quant = document.getElementById('hf-quant').value;
  const sort = document.getElementById('hf-sort').value;
  _showResults('搜索中...');
  try {
    const params = new URLSearchParams({ q, limit: '20', sort });
    if (modelType) params.set('type', modelType);
    if (quant) params.set('quant', quant);
    // Add timeout using AbortController
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s timeout
    const r = await fetch('/api/hf/search?' + params, { signal: controller.signal });
    clearTimeout(timeoutId);
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      _showResults('搜索失败: ' + (err.error || r.statusText));
      return;
    }
    const data = await r.json();
    if (data.error) {
      _showResults('API错误: ' + data.error);
      return;
    }
    renderHfResults(data);
  } catch (e) {
    if (e.name === 'AbortError') {
      _showResults('搜索超时（15秒），请重试或减少搜索条件');
    } else {
      _showResults('搜索出错: ' + e.message);
    }
  }
}

async function hfBrowse() {
  document.getElementById('hf-query').value = '';
  _showResults('加载中...');
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);
    const r = await fetch('/api/hf/search?q=&limit=30&sort=downloads', { signal: controller.signal });
    clearTimeout(timeoutId);
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      _showResults('加载失败: ' + (err.error || r.statusText));
      return;
    }
    const data = await r.json();
    if (data.error) {
      _showResults('API错误: ' + data.error);
      return;
    }
    renderHfResults(data);
  } catch (e) {
    if (e.name === 'AbortError') {
      _showResults('加载超时（15秒），请重试');
    } else {
      _showResults('加载出错: ' + e.message);
    }
  }
}

function _formatSize(bytes) {
  if (!bytes) return '';
  const gb = bytes / (1024 ** 3);
  return gb >= 1 ? gb.toFixed(1) + ' GB' : (bytes / (1024 ** 2)).toFixed(0) + ' MB';
}

function _formatDownloads(n) {
  return (n / 1000).toFixed(1) + 'k';
}

function _quantBadges(tags) {
  if (!tags || !Array.isArray(tags)) return '';
  const known = ['awq', 'gptq', 'gguf', 'fp8', 'bf16'];
  return tags.filter(t => known.includes(t.toLowerCase())).map(t => {
    const lo = t.toLowerCase();
    return '<span class="hf-badge ' + lo + '">' + lo.toUpperCase() + '</span>';
  }).join('');
}

function renderHfResults(models) {
  const area = document.getElementById('hf-results-area');
  if (!models || !models.length) { _showResults('未找到匹配的模型'); return; }
  area.innerHTML = '<div class="hf-results">' + models.map(function(m) {
    var name = m.modelId || m.id || 'unknown';
    var short = name.split('/').pop();
    var author = name.split('/')[0] || '';
    var tags = m.tags || [];
    var badgeHtml = _quantBadges(tags);
    var sizeHtml = (m.siblings && m.siblings.length > 0)
      ? '<br>' + _formatSize(m.siblings.find(function(s){return s.rfilename==='.gitattributes';}, m.siblings))
      : '';
    var typeLabel = m.pipeline_tag ? ' (' + m.pipeline_tag.replace(/-/g,' ') + ')' : '';
    var dlLink = 'https://huggingface.co/' + name;
    return '<div class="hf-card">' +
      '<div class="hf-card-info">' +
        '<div class="hf-card-name"><a href="' + dlLink + '" target="_blank" rel="noopener">' + short + '</a></div>' +
        '<div class="hf-card-meta">' + author + typeLabel + ' · ' + _formatDownloads(m.downloads || 0) + ' 次下载' +
        (badgeHtml ? ' · ' + badgeHtml : '') +
        '</div>' +
      '</div>' +
      '<div class="hf-card-actions">' +
        '<button class="btn btn-primary" style="font-size:12px" onclick="quickDownload(\\'' + name.replace(/'/g, "\\\\'") + '\\')">下载到 PaaS</button>' +
        '<a href="' + dlLink + '" target="_blank" rel="noopener" style="font-size:12px;color:var(--text-dim)">查看源页面 →</a>' +
      '</div>' +
    '</div>';
  }).join('') + '</div>';
}

// ── Download from search result ───────────────────────────────────────────

async function quickDownload(repoId) {
  document.getElementById('download-active-card').style.display = 'block';
  document.getElementById('dl-repo-id').textContent = repoId;
  document.getElementById('dl-repo-link').href = 'https://huggingface.co/' + repoId;
  document.getElementById('dl-progress-section').style.display = 'none';
  const log = document.getElementById('dl-log');
  log.textContent = 'Submitting download task: ' + repoId + '\\n';
  try {
    const r = await fetch('/api/models/download', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({repo_id: repoId, local_name: null})
    });
    const d = await r.json();
    if (d.error) { log.textContent = 'Error: ' + d.error; return; }
    _activeDlTaskId = d.task_id;
    pollProgress(d.task_id, log);
  } catch (e) {
    log.textContent = 'Submit failed: ' + e.message;
  }
}

// ── Model list (local) ────────────────────────────────────────────────────

async function loadModels() {
  const r = await fetch('/api/models/list');
  const d = await r.json();
  const el = document.getElementById('model-list');
  if (!d.models || !d.models.length) {
    el.innerHTML = '<div style="color:var(--text-dim);font-size:13px">暂无已下载模型</div>';
    return;
  }
  // Fetch active model and available models from Router
  var activeModel = null;
  var availableModels = {};
  try {
    const ar = await fetch('/api/models/available');
    const ad = await ar.json();
    activeModel = ad.active_model || null;
    (ad.models || []).forEach(function(m) {
      // Map model_path suffix to model_id for matching local models
      var pathParts = m.model_path.split('/');
      var dirName = pathParts[pathParts.length - 1];
      availableModels[dirName] = m;
    });
  } catch (e) { /* Router may be down */ }

  el.innerHTML = d.models.map(function(m) {
    var registered = availableModels[m.name];
    var isActive = registered && registered.is_active;
    var badge = isActive
      ? '<span style="background:#22c55e;color:#fff;font-size:10px;padding:2px 8px;border-radius:8px;margin-left:8px">运行中</span>'
      : '';
    var switchBtn = registered
      ? (isActive
        ? '<button class="btn" style="font-size:12px" disabled>当前模型</button>'
        : '<button class="btn btn-primary" style="font-size:12px" onclick="switchModel(\\'' + registered.model_id.replace(/'/g, "\\'") + '\\')">切换到此模型</button>')
      : '<span style="font-size:11px;color:var(--text-dim)">未注册</span>';
    return '<div class="container-row" style="align-items:flex-start;flex-wrap:wrap;gap:8px">' +
      '<div style="flex:1;min-width:200px">' +
        '<span class="name" style="font-family:monospace">' + m.name + '</span>' +
        '<span style="font-size:12px;color:var(--text-dim);margin-left:8px">' + m.size_gb + ' GB</span>' +
        badge +
      '</div>' +
      '<div class="btns" style="flex-shrink:0">' +
        switchBtn +
      '</div></div>';
  }).join('');
}

// ── Download progress polling ─────────────────────────────────────────────

function _fmtBytes(n) {
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
  if (n < 1073741824) return (n / 1048576).toFixed(1) + ' MB';
  return (n / 1073741824).toFixed(2) + ' GB';
}

function _fmtSpeed(bps) {
  if (bps <= 0) return '—';
  if (bps < 1048576) return (bps / 1024).toFixed(0) + ' KB/s';
  return (bps / 1048576).toFixed(1) + ' MB/s';
}

function _fmtEta(sec) {
  if (sec < 0 || sec > 604800) return '—';
  if (sec < 60) return Math.round(sec) + 's';
  if (sec < 3600) return Math.floor(sec / 60) + 'm ' + Math.round(sec % 60) + 's';
  return Math.floor(sec / 3600) + 'h ' + Math.floor((sec % 3600) / 60) + 'm';
}

function pollProgress(taskId, log) {
  if (_pollTimer) clearInterval(_pollTimer);
  _pollTimer = setInterval(async function() {
    try {
      const r = await fetch('/api/models/progress/' + taskId);
      const d = await r.json();
      log.textContent = d.log.join('\\n');
      log.scrollTop = log.scrollHeight;

      // Update progress UI
      var p = d.progress;
      if (p && p.total_bytes > 0) {
        document.getElementById('dl-progress-section').style.display = 'block';
        var pct = Math.min(100, Math.round((p.downloaded_bytes / p.total_bytes) * 100));
        document.getElementById('dl-progress-bar').style.width = pct + '%';
        document.getElementById('dl-progress-pct').textContent = pct + '%';
        document.getElementById('dl-progress-text').textContent =
          (p.completed_files || 0) + ' / ' + p.total_files + ' files';
        document.getElementById('dl-bytes').textContent =
          _fmtBytes(p.downloaded_bytes || 0) + ' / ' + _fmtBytes(p.total_bytes);

        if (p.current_file) {
          document.getElementById('dl-current-file').textContent = p.current_file.name || '—';
          document.getElementById('dl-speed').textContent = _fmtSpeed(p.current_file.speed_bps || 0);
          var eta = p.current_file.eta_seconds;
          // Calculate overall ETA based on overall speed
          if (p.downloaded_bytes > 0 && p.current_file.speed_bps > 0) {
            var remaining = p.total_bytes - p.downloaded_bytes;
            eta = remaining / p.current_file.speed_bps;
          }
          document.getElementById('dl-eta').textContent = _fmtEta(eta >= 0 ? eta : -1);
        }

        document.getElementById('dl-stall-warning').style.display =
          p.stall_warning ? 'block' : 'none';
      }

      if (d.status === 'done' || d.status === 'error') {
        clearInterval(_pollTimer);
        _activeDlTaskId = null;
        if (d.status === 'done') {
          document.getElementById('dl-progress-bar').style.width = '100%';
          document.getElementById('dl-progress-pct').textContent = '100%';
          document.getElementById('dl-current-file').textContent = 'Complete';
          document.getElementById('dl-speed').textContent = '—';
          document.getElementById('dl-eta').textContent = '—';
        }
        loadModels();
      }
    } catch (e) {
      // Network error during poll — keep trying
    }
  }, 1500);
}

// ── Model switch ──────────────────────────────────────────────────────────

async function switchModel(modelId) {
  if (!confirm('切换到 ' + modelId + '？这将重启 vLLM 容器（约 1-2 分钟）。')) return;
  try {
    const r = await fetch('/api/models/switch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({model_id: modelId})
    });
    const d = await r.json();
    if (d.error) {
      alert('❌ ' + d.error);
    } else {
      alert('✅ ' + (d.message || '模型切换已触发'));
    }
    loadModels();
  } catch (e) {
    alert('❌ 请求失败: ' + e.message);
  }
}

// ── Enter key triggers search ─────────────────────────────────────────────
document.getElementById('hf-query').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') { e.preventDefault(); hfSearch(); }
});

// ── Init ──────────────────────────────────────────────────────────────────
loadModels().catch(e => console.error('loadModels failed:', e));
loadPresetStatus().catch(e => console.error('loadPresetStatus failed:', e));
</script>
"""
    return page("模型管理", "/models", body)


@app.get("/api/hf/search")
async def api_hf_search(q: str = "", limit: int = 20, sort: str = "downloads", model_type: str = "", quant: str = ""):
    """Proxy to HuggingFace models API with search + filters."""
    # HF valid sorts: downloads, likes, createdAt, lastModified
    # "trending" is not valid — map to "likes" (closest semantic)
    hf_sort = sort if sort in ("downloads", "likes", "createdAt", "lastModified") else "downloads"
    params = {"search": q, "limit": min(limit, 50), "sort": hf_sort}
    if model_type:
        params["filter"] = model_type
    if quant:
        tags = params.get("filter", "")
        params["filter"] = f"{tags},{quant}" if tags else quant
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get("https://huggingface.co/api/models", params=params)
        data = r.json()
        if not isinstance(data, list):
            return JSONResponse({"error": f"HuggingFace API error: {data}"}, status_code=502)
        return JSONResponse(data)


@app.get("/api/hf/info/{repo_id:path}")
async def api_hf_info(repo_id: str):
    """Get detailed info for a single model from HuggingFace."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"https://huggingface.co/api/models/{repo_id}")
        if r.status_code == 404:
            return JSONResponse({"error": "Model not found"}, status_code=404)
        return JSONResponse(r.json())


@app.get("/api/hf/size/{repo_id:path}")
async def api_hf_size(repo_id: str):
    """Get total size of safetensors files for a model."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"https://huggingface.co/api/models/{repo_id}")
        if r.status_code == 404:
            return JSONResponse({"error": "Model not found"}, status_code=404)
        data = r.json()
        siblings = data.get("siblings", [])
        total = sum(s.get("size", 0) or 0 for s in siblings if s.get("rfilename", "").endswith(".safetensors"))
        return JSONResponse({
            "total_bytes": total,
            "total_gb": round(total / (1024 ** 3), 2),
            "safetensors_count": sum(1 for s in siblings if s.get("rfilename", "").endswith(".safetensors")),
        })


@app.get("/api/models/list")
async def api_models_list():
    models = _scan_models(MODELS_ROOT)
    return JSONResponse({"models": models, "models_root": MODELS_ROOT})


@app.post("/api/models/download")
async def api_models_download(request: Request):
    body = await request.json()
    repo_id: str = body.get("repo_id", "").strip()
    local_name: str = body.get("local_name", "").strip()
    if not repo_id:
        return JSONResponse({"error": "repo_id 不能为空"}, status_code=400)
    # Derive local dir name from repo_id if not provided
    if not local_name:
        local_name = repo_id.split("/")[-1].lower()
    local_dir = str(Path(MODELS_ROOT) / local_name)
    task_id = str(uuid.uuid4())[:8]
    _download_tasks[task_id] = {
        "status": "running",
        "log": [],
        "repo_id": repo_id,
        "local_dir": local_dir,
        "progress": {
            "total_files": 0,
            "completed_files": 0,
            "total_bytes": 0,
            "downloaded_bytes": 0,
            "current_file": None,
            "last_update": time.time(),
            "stall_warning": False,
            "file_list": [],
        },
    }
    t = threading.Thread(
        target=_run_download,
        args=(task_id, repo_id, local_dir, HF_TOKEN or None),
        daemon=True,
    )
    t.start()
    return JSONResponse({"task_id": task_id, "local_dir": local_dir})


@app.get("/api/models/progress/{task_id}")
async def api_models_progress(task_id: str):
    task = _download_tasks.get(task_id)
    if not task:
        return JSONResponse({"error": "任务不存在"}, status_code=404)
    prog = task.get("progress", {})
    # Strip internal keys (prefixed with _)
    progress_clean = {k: v for k, v in prog.items() if not k.startswith("_")}
    return JSONResponse({
        "status": task["status"],
        "log": task["log"],
        "repo_id": task.get("repo_id", ""),
        "local_dir": task.get("local_dir", ""),
        "progress": progress_clean,
    })


@app.post("/api/models/switch")
async def api_models_switch(request: Request):
    """
    Switch active LLM model via Router API.
    Delegates to Router's /v1/models/switch which handles container orchestration.
    """
    body = await request.json()
    model_id: str = body.get("model_id", "").strip()
    if not model_id:
        return JSONResponse({"error": "model_id is required"}, status_code=400)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{LITELLM_BASE_URL.rstrip('/v1')}/v1/models/switch",
                json={"model_id": model_id},
                headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
            )
            data = resp.json()
            if resp.status_code >= 400:
                return JSONResponse(
                    {"error": data.get("detail", str(data))},
                    status_code=resp.status_code,
                )
            return JSONResponse(data)
    except httpx.ConnectError:
        return JSONResponse({"error": "Cannot connect to Router service"}, status_code=502)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/models/available")
async def api_models_available():
    """Proxy to Router's /v1/models/available — list switchable models with status."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{LITELLM_BASE_URL.rstrip('/v1')}/v1/models/available",
                headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
            )
            return JSONResponse(resp.json())
    except Exception:
        return JSONResponse({"models": [], "active_model": None, "error": "Router unavailable"})
# ══════════════════════════════════════════════════════════════════════════════

# Containers available for log viewing (all managed + infra containers)
LOG_CONTAINERS = [
    "ai_vllm_qwen", "ai_vllm_gemma", "ai_whisper", "ai_comfyui",
    "ai_router", "ai_router_worker", "ai_router_redis", "ai_webapp",
]


@app.get("/logs", response_class=HTMLResponse)
async def logs_page():
    container_opts = "".join(
        f'<option value="{c}">{c}</option>' for c in LOG_CONTAINERS
    )
    body = f"""
<div class="card">
  <h2>容器日志</h2>
  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
    <div class="form-group" style="margin-bottom:0;min-width:180px">
      <label>容器</label>
      <select id="log-container">{container_opts}</select>
    </div>
    <div class="form-group" style="margin-bottom:0;min-width:120px">
      <label>最后行数</label>
      <select id="log-tail">
        <option value="100">100 行</option>
        <option value="200">200 行</option>
        <option value="500">500 行</option>
        <option value="1000">1000 行</option>
        <option value="all">全部</option>
      </select>
    </div>
    <div class="form-group" style="margin-bottom:0;min-width:160px">
      <label>时间范围</label>
      <select id="log-since">
        <option value="">全部时间</option>
        <option value="5m">最近 5 分钟</option>
        <option value="30m">最近 30 分钟</option>
        <option value="1h">最近 1 小时</option>
        <option value="6h">最近 6 小时</option>
        <option value="24h">最近 24 小时</option>
      </select>
    </div>
    <div style="display:flex;gap:8px;padding-bottom:0">
      <button class="btn btn-primary" onclick="fetchLogs()">📋 加载日志</button>
      <button class="btn btn-ghost" onclick="copyLogs()">📋 复制</button>
      <button class="btn btn-ghost" onclick="clearView()">🗑 清空显示</button>
    </div>
  </div>
  <div id="log-meta" style="font-size:12px;color:var(--text-dim);margin-bottom:8px"></div>
  <div id="log-box" style="
    background:var(--bg); border:1px solid var(--border); border-radius:6px;
    padding:12px; font-family:monospace; font-size:12px; line-height:1.6;
    white-space:pre-wrap; word-break:break-all;
    max-height:600px; overflow-y:auto; min-height:120px;
    color:var(--text-dim);
  ">请选择容器并点击「加载日志」</div>
  <div style="font-size:11px;color:var(--text-dim);margin-top:8px">
    ⚠️ 要永久清除日志文件，需在服务器上执行：
    <code style="background:var(--bg);padding:2px 6px;border-radius:3px">
    sudo truncate -s 0 $(docker inspect --format='{{{{.LogPath}}}}' &lt;容器名&gt;)</code>
  </div>
</div>

<script>
async function fetchLogs() {{
  var container = document.getElementById('log-container').value;
  var tail = document.getElementById('log-tail').value;
  var since = document.getElementById('log-since').value;
  var box = document.getElementById('log-box');
  var meta = document.getElementById('log-meta');

  box.textContent = '加载中…';
  meta.textContent = '';

  try {{
    var params = new URLSearchParams({{tail: tail}});
    if (since) params.append('since', since);
    var r = await fetch('/api/logs/' + container + '?' + params.toString());
    if (!r.ok) throw new Error('HTTP ' + r.status);
    var d = await r.json();
    if (d.error) {{
      box.textContent = '❌ ' + d.error;
      return;
    }}
    box.textContent = d.lines.join('\\n') || '（无日志）';
    box.scrollTop = box.scrollHeight;
    meta.textContent = '共 ' + d.count + ' 行 · 容器: ' + container + (since ? ' · 时间范围: ' + since : '');
  }} catch(e) {{
    box.textContent = '加载失败: ' + e.message;
  }}
}}

function copyLogs() {{
  var text = document.getElementById('log-box').textContent;
  navigator.clipboard.writeText(text).then(function() {{
    alert('已复制到剪贴板 (' + text.split('\\n').length + ' 行)');
  }}).catch(function() {{
    var ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    alert('已复制');
  }});
}}

function clearView() {{
  document.getElementById('log-box').textContent = '（已清空显示）';
  document.getElementById('log-meta').textContent = '';
}}
</script>
"""
    return page("容器日志", "/logs", body)


@app.get("/api/logs/{container_name}")
async def api_logs(container_name: str, tail: str = "200", since: str = ""):
    if container_name not in LOG_CONTAINERS:
        return JSONResponse({"error": f"容器 {container_name} 不在允许列表中"}, status_code=403)

    def _get_logs():
        import datetime as dt
        dc = docker.from_env()
        try:
            c = dc.containers.get(container_name)
        except docker.errors.NotFound:
            return {"error": f"容器 {container_name} 不存在", "lines": [], "count": 0}

        kwargs: dict = {"timestamps": True, "stream": False}

        # tail
        if tail != "all":
            try:
                kwargs["tail"] = int(tail)
            except ValueError:
                kwargs["tail"] = 200

        # since
        if since:
            unit = since[-1]
            try:
                val = int(since[:-1])
            except ValueError:
                val = 0
            delta = None
            if unit == "m":
                delta = dt.timedelta(minutes=val)
            elif unit == "h":
                delta = dt.timedelta(hours=val)
            if delta:
                kwargs["since"] = dt.datetime.now(dt.timezone.utc) - delta

        raw = c.logs(**kwargs)
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
        else:
            text = "".join(chunk.decode("utf-8", errors="replace") for chunk in raw)

        # Convert UTC timestamps to local time
        # Docker format: 2026-04-09T14:38:13.900263386Z ...
        import re
        local_tz = dt.datetime.now(dt.timezone.utc).astimezone().tzinfo

        def _utc_to_local(match):
            ts_str = match.group(0)
            try:
                # Parse ISO timestamp (strip nanoseconds beyond microseconds)
                clean = re.sub(r"(\.\d{6})\d+", r"\1", ts_str.rstrip("Z"))
                utc_dt = dt.datetime.fromisoformat(clean).replace(tzinfo=dt.timezone.utc)
                local_dt = utc_dt.astimezone(local_tz)
                return local_dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return ts_str

        text = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z", _utc_to_local, text)

        lines = [l for l in text.splitlines() if l.strip()]
        return {"lines": lines, "count": len(lines)}

    result = await asyncio.to_thread(_get_logs)
    return JSONResponse(result)


# ── Queue Page ───────────────────────────────────────────────────────────────
ROUTER_URL = os.getenv("ROUTER_URL", "http://ai_router:4001")


@app.get("/queue", response_class=HTMLResponse)
async def get_queue_page():
    body = """
<style>
  #queue-box { font-family: monospace; white-space: pre-wrap; background: #111; color: #0f0;
              padding: 12px; border-radius: 8px; max-height: 70vh; overflow-y: auto; min-height: 100px; }
  #queue-status { margin-bottom: 12px; }
  #queue-actions { margin-top: 12px; }
  #queue-actions button { padding: 6px 16px; margin-right: 8px; }
</style>
<h2>任务队列</h2>
<p id="queue-status">加载队列状态...</p>

<div id="queue-box">—</div>

<div id="queue-actions">
  <button onclick="refreshQueue()">刷新</button>
  <button onclick="clearViewQueue()">清空显示</button>
  <button onclick="autoRefreshQueue()">自动刷新: 开</button>
</div>

<script>
let queueAuto = true;

async function refreshQueue() {
  const box = document.getElementById('queue-box');
  const status = document.getElementById('queue-status');

  try {
    const [qResp, tResp] = await Promise.all([
      fetch('/api/queue'),
      fetch('/status')
    ]);

    const qData = qResp.ok ? await qResp.json() : {error: '请求失败'};
    const tData = tResp.ok ? await tResp.json() : {};

    status.textContent = '队列: ' + (qData.queue_size || 0) + ' 个任务 | ' +
      ['ai_vllm_qwen', 'ai_vllm_gemma', 'ai_whisper', 'ai_comfyui']
        .map(c => c + ': ' + (tData.containers && tData.containers[c] || '未知'))
        .join(' | ');

    if (qData.tasks && qData.tasks.length > 0) {
      box.textContent = qData.tasks.map(t =>
        `[${t.status}] [${t.type || 'unknown'}] ${t.id} (celery: ${t.celery_id || 'N/A'})
  入队: ${t.enqueued_at}
  数据: ${JSON.stringify(t.payload || {})}`
      ).join('\\n\\n');
    } else {
      box.textContent = '（队列中无任务）';
    }
  } catch(e) {
    box.textContent = '加载失败: ' + e.message;
  }
}

function clearViewQueue() {
  document.getElementById('queue-box').textContent = '（已清空显示）';
}

function autoRefreshQueue() {
  queueAuto = !queueAuto;
  const btns = document.querySelectorAll('#queue-actions button');
  btns[2].textContent = '自动刷新: ' + (queueAuto ? '开' : '关');
}

// Auto-refresh every 10s
setInterval(() => { if (queueAuto) refreshQueue(); }, 10000);

// Initial load
refreshQueue();
</script>
"""
    return page("任务队列", "/queue", body)


# ── Queue API proxy (routes to router) ───────────────────────────────────────
@app.get("/api/queue")
async def api_queue():
    """Proxy queue data from router API."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(ROUTER_URL.rstrip('/') + "/api/v1/queue")
            return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as e:
        return JSONResponse({"error": str(e), "tasks": [], "queue_size": 0})


# ── ComfyUI preset models (matches services/comfyui/setup.sh) ─────────────────
COMFYUI_MODELS = {
    "sd15": {
        "label": "SD 1.5",
        "files": [f"{MODELS_ROOT}/comfyui/checkpoints/v1-5-pruned-emaonly.safetensors"],
        "size_gb": 4.0,
        "desc": "Stable Diffusion 1.5 - 基础文生图模型",
    },
    "sdxl": {
        "label": "SDXL Base",
        "files": [f"{MODELS_ROOT}/comfyui/checkpoints/sd_xl_base_1.0.safetensors"],
        "size_gb": 7.0,
        "desc": "Stable Diffusion XL - 高质量文生图",
    },
    "cogvideo_transformer": {
        "label": "CogVideoX Transformer",
        "dirs": [f"{MODELS_ROOT}/comfyui/diffusion_models/cogvideox5b"],
        "size_gb": 11.14,
        "desc": "CogVideoX-5B 核心模型（分片1+2）",
    },
    "cogvideo_vae": {
        "label": "CogVideoX VAE",
        "files": [f"{MODELS_ROOT}/comfyui/vae/cogvideox5b_vae.safetensors"],
        "size_gb": 0.86,
        "desc": "CogVideoX 视频编解码器",
    },
    "cogvideo_t5": {
        "label": "CogVideoX T5-XXL (fp8)",
        "files": [f"{MODELS_ROOT}/comfyui/text_encoders/t5xxl_fp8_e4m3fn.safetensors"],
        "size_gb": 4.9,
        "desc": "T5-XXL fp8 文本编码器（CLIPLoader 单文件版）",
    },
    "cogvideo_t5_bf16": {
        "label": "CogVideoX T5-XXL (BF16 shards)",
        "dirs": [f"{MODELS_ROOT}/comfyui/text_encoders/t5xxl"],
        "size_gb": 9.5,
        "desc": "T5-XXL BF16 原始分片（参考用）",
    },
    "cogvideo_tokenizer": {
        "label": "CogVideoX Tokenizer",
        "dirs": [f"{MODELS_ROOT}/comfyui/tokenizers/t5xxl"],
        "size_gb": 0.1,
        "desc": "T5-XXL tokenizer 文件",
    },
    "liveportrait_1": {
        "label": "LivePortrait - appearance",
        "files": [f"{MODELS_ROOT}/comfyui/liveportrait/appearance_feature_extractor.pth"],
        "size_gb": 0.05,
        "desc": "",
        "download_url": "https://huggingface.co/KlingTeam/LivePortrait/resolve/main/liveportrait/base_models/appearance_feature_extractor.pth",
    },
    "liveportrait_2": {
        "label": "LivePortrait - motion",
        "files": [f"{MODELS_ROOT}/comfyui/liveportrait/motion_extractor.pth"],
        "size_gb": 0.05,
        "desc": "",
        "download_url": "https://huggingface.co/KlingTeam/LivePortrait/resolve/main/liveportrait/base_models/motion_extractor.pth",
    },
    "liveportrait_3": {
        "label": "LivePortrait - generator",
        "files": [f"{MODELS_ROOT}/comfyui/liveportrait/spade_generator.pth"],
        "size_gb": 0.2,
        "desc": "",
        "download_url": "https://huggingface.co/KlingTeam/LivePortrait/resolve/main/liveportrait/base_models/spade_generator.pth",
    },
    "liveportrait_4": {
        "label": "LivePortrait - warping",
        "files": [f"{MODELS_ROOT}/comfyui/liveportrait/warping_module.pth"],
        "size_gb": 0.05,
        "desc": "",
        "download_url": "https://huggingface.co/KlingTeam/LivePortrait/resolve/main/liveportrait/base_models/warping_module.pth",
    },
    "liveportrait_5": {
        "label": "LivePortrait - stitching",
        "files": [f"{MODELS_ROOT}/comfyui/liveportrait/stitching_retargeting_module.pth"],
        "size_gb": 0.05,
        "desc": "",
        "download_url": "https://huggingface.co/KlingTeam/LivePortrait/resolve/main/liveportrait/retargeting_models/stitching_retargeting_module.pth",
    },
}

@app.get("/api/comfyui/model-status")
async def api_comfyui_model_status():
    """Check which ComfyUI preset models are present on disk."""
    results = {}
    total_size_gb = 0
    for key, cfg in COMFYUI_MODELS.items():
        files = cfg.get("files", [])
        dirs = cfg.get("dirs", [])
        size_gb = cfg.get("size_gb", 0)

        # Check files - consider any non-empty file as present
        files_ok = []
        for f in files:
            exists = os.path.isfile(f) and os.path.getsize(f) > 1024  # at least 1KB
            files_ok.append(exists)

        # Check directories - any directory with at least one file
        dirs_ok = []
        for d in dirs:
            is_ok = os.path.isdir(d) and any(os.path.isfile(os.path.join(d, f)) for f in os.listdir(d) if not f.startswith('.'))
            dirs_ok.append(is_ok)

        all_checks = files_ok + dirs_ok
        total = len(all_checks)
        present = sum(all_checks) if total > 0 else 0

        results[key] = {
            "label": cfg["label"],
            "desc": cfg.get("desc", ""),
            "total": total,
            "present": present,
            "ready": present == total if total > 0 else False,
            "size_gb": size_gb,
            "missing_files": [f for f, ok in zip(files, files_ok) if not ok],
            "missing_dirs": [d for d, ok in zip(dirs, dirs_ok) if not ok] if dirs else [],
        }
        if present == total:
            total_size_gb += size_gb

    # Group into workflows
    workflows = {
        "sd_workflow": {
            "label": "文生图 — SD 1.5",
            "models": ["sd15"],
            "ready": all(results[k]["ready"] for k in ["sd15"]),
            "total_size": results["sd15"]["size_gb"] if "sd15" in results else 0,
        },
        "sdxl_workflow": {
            "label": "文生图 — SDXL",
            "models": ["sdxl"],
            "ready": all(results[k]["ready"] for k in ["sdxl"]),
            "total_size": results["sdxl"]["size_gb"] if "sdxl" in results else 0,
        },
        "cogvideo_workflow": {
            "label": "图生视频 — CogVideoX-5B",
            "models": ["cogvideo_transformer", "cogvideo_vae", "cogvideo_t5", "cogvideo_tokenizer"],
            "ready": all(results[k]["ready"] for k in ["cogvideo_transformer", "cogvideo_vae", "cogvideo_t5", "cogvideo_tokenizer"]),
            "total_size": sum(results[k]["size_gb"] for k in ["cogvideo_transformer", "cogvideo_vae", "cogvideo_t5", "cogvideo_tokenizer"]),
        },
        "liveportrait_workflow": {
            "label": "数字人 — LivePortrait",
            "models": ["liveportrait_1", "liveportrait_2", "liveportrait_3", "liveportrait_4", "liveportrait_5"],
            "ready": all(results[k]["ready"] for k in ["liveportrait_1", "liveportrait_2", "liveportrait_3", "liveportrait_4", "liveportrait_5"]),
            "total_size": sum(results[k]["size_gb"] for k in ["liveportrait_1", "liveportrait_2", "liveportrait_3", "liveportrait_4", "liveportrait_5"]),
        },
    }

    return JSONResponse({
        "models": results,
        "workflows": workflows,
        "total_ready_size_gb": total_size_gb,
        "hdd_path": COMFYUI_MODELS_HDD,
        "hdd_set": bool(COMFYUI_MODELS_HDD),
    })


# ── Preset model download (ComfyUI workflows) ─────────────────────────────
_preset_download_tasks: dict = {}


def _run_preset_download(task_id: str, model_keys: list[str]):
    """Background thread: download missing ComfyUI preset models."""
    import httpx as sync_httpx
    task = _preset_download_tasks[task_id]
    task["status"] = "running"

    for i, key in enumerate(model_keys):
        cfg = COMFYUI_MODELS.get(key)
        if not cfg:
            task["log"].append(f"[{i+1}/{len(model_keys)}] Unknown model: {key}")
            continue

        url = cfg.get("download_url")
        if not url:
            task["log"].append(f"[{i+1}/{len(model_keys)}] {cfg['label']}: no download URL configured")
            continue

        target_file = cfg["files"][0] if cfg.get("files") else None
        if not target_file:
            task["log"].append(f"[{i+1}/{len(model_keys)}] {cfg['label']}: no target file defined")
            continue

        # Skip if already downloaded (>1KB)
        if os.path.isfile(target_file) and os.path.getsize(target_file) > 1024:
            task["log"].append(f"[{i+1}/{len(model_keys)}] {cfg['label']}: already exists, skipping")
            task["completed_files"] += 1
            continue

        task["current_file"] = cfg["label"]
        task["log"].append(f"[{i+1}/{len(model_keys)}] Downloading {cfg['label']} from {url}")

        try:
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            with sync_httpx.Client(timeout=300, follow_redirects=True) as client:
                with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", 0))
                    task["current_total_bytes"] = total
                    task["current_downloaded_bytes"] = 0

                    with open(target_file, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=65536):
                            f.write(chunk)
                            task["current_downloaded_bytes"] += len(chunk)
                            task["total_downloaded_bytes"] += len(chunk)

            size_mb = os.path.getsize(target_file) / (1024 * 1024)
            task["log"].append(f"  ✓ {cfg['label']} downloaded ({size_mb:.1f} MB)")
            task["completed_files"] += 1
        except Exception as e:
            task["log"].append(f"  ✗ {cfg['label']} failed: {str(e)}")
            task["errors"] += 1

    task["status"] = "done" if task["errors"] == 0 else "error"
    task["current_file"] = None
    task["log"].append(f"Download complete: {task['completed_files']}/{len(model_keys)} files, {task['errors']} errors")


@app.post("/api/comfyui/download-preset")
async def api_comfyui_download_preset(req: dict):
    """Download missing models for a ComfyUI preset workflow."""
    workflow_key = req.get("workflow_key", "")

    # Build workflow definitions (same as model-status endpoint)
    workflow_defs = {
        "sd_workflow": ["sd15"],
        "cogvideo_workflow": ["cogvideo_transformer", "cogvideo_vae", "cogvideo_t5", "cogvideo_tokenizer"],
        "liveportrait_workflow": ["liveportrait_1", "liveportrait_2", "liveportrait_3", "liveportrait_4", "liveportrait_5"],
    }

    if workflow_key not in workflow_defs:
        return JSONResponse({"error": f"Unknown workflow: {workflow_key}"}, status_code=400)

    # Find missing models (no file or file < 1KB = stub)
    model_keys = workflow_defs[workflow_key]
    missing = []
    for key in model_keys:
        cfg = COMFYUI_MODELS.get(key, {})
        files = cfg.get("files", [])
        if not cfg.get("download_url"):
            continue  # No URL, skip
        for f in files:
            if not os.path.isfile(f) or os.path.getsize(f) < 1024:
                missing.append(key)
                break

    if not missing:
        return JSONResponse({"error": "All models already present", "already_complete": True})

    task_id = f"preset_{workflow_key}_{int(time.time())}"
    total_size = sum(COMFYUI_MODELS.get(k, {}).get("size_gb", 0) for k in missing)
    _preset_download_tasks[task_id] = {
        "status": "starting",
        "log": [f"Starting download: {len(missing)} models (~{total_size:.1f} GB)"],
        "total_files": len(missing),
        "completed_files": 0,
        "errors": 0,
        "current_file": None,
        "current_total_bytes": 0,
        "current_downloaded_bytes": 0,
        "total_downloaded_bytes": 0,
    }

    thread = threading.Thread(target=_run_preset_download, args=(task_id, missing), daemon=True)
    thread.start()

    return JSONResponse({"task_id": task_id, "missing_count": len(missing)})


@app.get("/api/comfyui/download-progress/{task_id}")
async def api_comfyui_download_progress(task_id: str):
    """Poll download progress for a preset workflow."""
    task = _preset_download_tasks.get(task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    return JSONResponse({
        "status": task["status"],
        "log": task["log"],
        "total_files": task["total_files"],
        "completed_files": task["completed_files"],
        "errors": task["errors"],
        "current_file": task["current_file"],
        "current_total_bytes": task["current_total_bytes"],
        "current_downloaded_bytes": task["current_downloaded_bytes"],
        "total_downloaded_bytes": task["total_downloaded_bytes"],
    })


# ── Built-in workflow browser ───────────────────────────────────────────────
# Maps workflow filename prefix to the model-status workflow key
_WORKFLOW_MODEL_MAP = {
    "01_image_sd15":       "sd_workflow",
    "02_image_sdxl":       "sdxl_workflow",
    "03_video_cogvideox":  "cogvideo_workflow",
    "04_video_cogvideox":  "cogvideo_workflow",
    "05_digital_human":    "liveportrait_workflow",
    "06_digital_human":    "liveportrait_workflow",
}

_WORKFLOW_ICONS = {
    "01": "\U0001f5bc\ufe0f",   # framed picture
    "02": "\U0001f3a8",         # palette
    "03": "\U0001f3ac",         # clapper
    "04": "\U0001f3ac",         # clapper
    "05": "\U0001f9d1",         # person
    "06": "\U0001f60a",         # smile
}

_WORKFLOW_CATEGORIES = {
    "01": "image",
    "02": "image",
    "03": "video",
    "04": "video",
    "05": "digital_human",
    "06": "digital_human",
}


@app.get("/api/comfyui/workflows")
async def api_comfyui_workflows():
    """List all built-in ComfyUI workflows with metadata."""
    wf_dir = Path(COMFYUI_WORKFLOWS_DIR)
    if not wf_dir.is_dir():
        return JSONResponse({"workflows": [], "error": "Workflows directory not found"})

    workflows = []
    for fp in sorted(wf_dir.glob("*.json")):
        try:
            data = json.loads(fp.read_text())
        except Exception:
            continue
        info = data.get("extra", {}).get("info", {})
        prefix = fp.stem[:2]
        # Find matching model group key
        model_group = None
        for pat, group in _WORKFLOW_MODEL_MAP.items():
            if fp.stem.startswith(pat):
                model_group = group
                break

        workflows.append({
            "id": fp.stem,
            "filename": fp.name,
            "name": info.get("name", fp.stem),
            "description": info.get("description", ""),
            "icon": _WORKFLOW_ICONS.get(prefix, "\U0001f4c4"),
            "category": _WORKFLOW_CATEGORIES.get(prefix, "other"),
            "model_group": model_group,
        })

    return JSONResponse({"workflows": workflows})


@app.get("/api/comfyui/workflows/{filename}")
async def api_comfyui_workflow_download(filename: str):
    """Download a single built-in workflow JSON file."""
    # Sanitize: only allow .json files, no path traversal
    if not filename.endswith(".json") or "/" in filename or "\\" in filename or ".." in filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)

    fp = Path(COMFYUI_WORKFLOWS_DIR) / filename
    if not fp.is_file():
        return JSONResponse({"error": "Workflow not found"}, status_code=404)

    content = fp.read_bytes()
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/container/stop/{container_name}")
async def stop_container(container_name: str):
    """Stop a specific container (GPU containers only)"""
    if container_name not in GPU_MANAGED_CONTAINERS:
        return JSONResponse({"error": f"容器 {container_name} 不在允许列表中"}, status_code=403)
    try:
        dc = docker.from_env()
        try:
            c = dc.containers.get(container_name)
            c.stop(timeout=15)
            return JSONResponse({"ok": True})
        except docker.errors.NotFound:
            # Container not running, that's ok
            return JSONResponse({"ok": True, "message": "Container not running"})
    except Exception as e:
        return JSONResponse({"error": str(e)})

