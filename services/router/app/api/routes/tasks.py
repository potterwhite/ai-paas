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
