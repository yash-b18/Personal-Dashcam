"""
DashcamIQ — FastAPI application entry point.

Run with:
    uvicorn app:app --reload
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.routes.anomalies import router as anomalies_router
from api.routes.health import router as health_router
from api.routes.labels import router as labels_router
from api.routes.scores import router as scores_router
from api.routes.videos import router as videos_router


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup and shutdown."""
    # Startup: validate config, warm up connections
    get_settings()
    yield
    # Shutdown: nothing to tear down (connections managed per-request)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title="DashcamIQ API",
        description="Dashcam anomaly detection and driver scoring platform",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health_router)
    application.include_router(videos_router, prefix="/api/v1")
    application.include_router(anomalies_router, prefix="/api/v1")
    application.include_router(labels_router, prefix="/api/v1")
    application.include_router(scores_router, prefix="/api/v1")

    return application


app = create_app()
