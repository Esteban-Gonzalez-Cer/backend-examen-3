"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.data.db import create_engine, create_sessionmaker
from app.integration.sii.client import build_http_client
from app.interaction.error_handlers import register_error_handlers
from app.interaction.routers import admin, auth, students, whatif

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.http_client = build_http_client(settings.sii_base_url, settings.sii_timeout_seconds)
        url = settings.async_database_url
        if url.startswith("sqlite"):
            logger.warning("Using local SQLite (%s). Set DATABASE_URL to your Supabase pooler URL.", url)
        app.state.engine = create_engine(url)
        app.state.sessionmaker = create_sessionmaker(app.state.engine)
        try:
            yield
        finally:
            await app.state.http_client.aclose()
            await app.state.engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "Backend propio que actúa como intermediario seguro con el SII ITC y aloja el "
            "What-If Simulator (retícula como DAG, ruta crítica y cuellos de botella)."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_error_handlers(app)

    api = APIRouter(prefix="/api/v1")
    for module in (auth, students, whatif, admin):
        api.include_router(module.router)
    app.include_router(api)

    @app.get("/health", tags=["ops"], summary="Health check for the hosting platform")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
