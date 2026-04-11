from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Router liveness probe."""
    return {"status": "ok"}
