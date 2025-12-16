from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.clusters import router as clusters_router
from app.api.ingest import router as ingest_router
from app.config import settings
from app.db import check_db_connection, close_db
from app.logging_config import configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    yield
    await close_db()


app = FastAPI(
    title="InsightThreads Backend",
    description="Backend API for InsightThreads - Document analysis and insights platform",
    debug=settings.DEBUG,
    lifespan=lifespan,
)


app.include_router(auth_router)
app.include_router(ingest_router)
app.include_router(clusters_router)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> JSONResponse:
    """
    Health check endpoint.
    
    Returns:
        JSON response with health status and database connection status.
    """
    db_healthy = await check_db_connection()
    status_code = status.HTTP_200_OK if db_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if db_healthy else "unhealthy",
            "database": "connected" if db_healthy else "disconnected",
        },
    )


@app.get("/", status_code=status.HTTP_200_OK)
async def root() -> dict:
    """Root endpoint."""
    return {
        "message": "InsightThreads Backend API",
    }
