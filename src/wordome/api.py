import uvicorn
from fastapi import FastAPI

from wordome.infrastructure import WebFetcherManager

# Create the FastAPI app
app = FastAPI(
    title="Wordome API",
    description="Web scraping and word frequency analysis",
)

# Create a single fetcher instance (reused for all requests)
web_fetcher_manager = WebFetcherManager()


@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "service": "Wordome API",
        "status": "running",
        "message": "Welcome to the Wordome!",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "fetcher_ready": web_fetcher_manager is not None
    }


if __name__ == "__main__":
    """
    Standalone execution for debugging purposes only
    """
    uvicorn.run(app, host="127.0.0.1", port=8000)
