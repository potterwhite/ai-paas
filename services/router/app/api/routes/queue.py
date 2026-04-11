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
"""Queue inspection — Phase 4.4."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.celery_app import celery_app

router = APIRouter()

# In-memory task tracker for queued items (supplemented by Celery broker)
_queue: list[dict] = []


@router.get("/queue")
async def get_queue():
    """Return current queue status from Celery + in-memory tracker."""
    try:
        inspector = celery_app.control.inspect()
        reserved = inspector.reserved() or {}
        queue_size = sum(len(v) for v in reserved.values())
    except Exception:
        queue_size = len(_queue)

    return {
        "queue_size": queue_size,
        "tasks": _queue[-50:],  # last 50
    }


@router.post("/queue")
async def enqueue_task(payload: dict):
    """Add a task to the queue."""
    task_entry = {
        "id": f"task_{len(_queue)+1}",
        "type": payload.get("type", "unknown"),
        "status": "queued",
        "payload": payload,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
    }
    _queue.append(task_entry)

    # Also submit to Celery
    task = celery_app.send_task("tasks.switch_gpu_mode", args=[payload])
    task_entry["celery_id"] = task.id

    return task_entry


@router.delete("/queue/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a queued task."""
    global _queue
    _queue = [t for t in _queue if t["id"] != task_id]
    # Attempt Celery revoke
    try:
        celery_app.control.revoke(task_id, terminate=True)
    except Exception:
        pass
    return {"success": True}
