import uvicorn
from fastapi import FastAPI

from wordome.routes import health, sandbox

# Initialize app
app = FastAPI(
    title="Wordome API",
    description="Web scraping and word frequency analysis",
)
# Include routers
app.include_router(health.router)
app.include_router(sandbox.router)

if __name__ == "__main__":
    """
    Standalone execution for debugging purposes only
    """
    uvicorn.run(app, host="127.0.0.1", port=8000)
