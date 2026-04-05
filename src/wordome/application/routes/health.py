from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "service": "Wordome API",
        "status": "running",
        "message": "Welcome to the Wordome!",
    }
