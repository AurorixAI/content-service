"""Content Service — FastAPI Application"""
from __future__ import annotations

import logging
import logging.config
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.content_router import router as content_router
from src.api.router import router
from src.core.config import get_settings
from src.core.middleware import RequestIDMiddleware, configure_logging

settings = get_settings()
configure_logging(is_development=settings.is_development)
log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(content_router)

    # Static раздача вырезанных рисунков учебников
    figures_dir = Path(settings.figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.figures_url_prefix,
        StaticFiles(directory=str(figures_dir)),
        name="figures",
    )

    Instrumentator(excluded_handlers=["/metrics", "/api/v1/health/live", "/api/v1/health/ready"]).instrument(app).expose(app)

    @app.on_event("startup")
    async def startup() -> None:
        log.info("%s v%s starting up", settings.app_name, settings.app_version)

    return app


app = create_app()
