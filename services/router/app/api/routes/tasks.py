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
"""Task status — Phase 4.4."""

from fastapi import APIRouter

from app.core.celery_app import celery_app

router = APIRouter()


@router.get("/tasks")
async def list_tasks():
    """List recent Celery tasks."""
    try:
        inspector = celery_app.control.inspect()
        active = inspector.active() or {}
        scheduled = inspector.scheduled() or {}
        reserved = inspector.reserved() or {}
        return {
            "active": sum(len(v) for v in active.values()),
            "scheduled": sum(len(v) for v in scheduled.values()),
            "reserved": sum(len(v) for v in reserved.values()),
        }
    except Exception as e:
        return {"error": f"Celery unavailable: {e}"}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get Celery task status."""
    result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }


@router.post("/tasks")
async def create_task(payload: dict):
    """Submit a task directly (for testing)."""
    task_type = payload.get("type", "switch_gpu_mode")
    task = celery_app.send_task(
        f"tasks.{task_type}",
        args=[payload.get("args", {})],
    )
    return {"task_id": task.id, "status": "submitted"}
