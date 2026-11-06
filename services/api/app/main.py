from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.database import Database
from app.errors import SpatialApiError
from app.routers import health, layers, tiles
from app.services.registry import SpatialRegistry

LOGGER = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(app_settings)
        registry = SpatialRegistry(app_settings, database)
        app.state.settings = app_settings
        app.state.database = database
        app.state.registry = registry

        await database.open()
        LOGGER.info(
            "Spatial API started (database=%s, schemas=%s)",
            "configured" if database.configured else "not configured",
            ",".join(app_settings.schemas),
        )
        try:
            yield
        finally:
            await database.close()

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        description=(
            "Read-only PostGIS vector API for MapLibre. Serves layer metadata, "
            "MVT tiles, GeoJSON features and extents without GeoServer."
        ),
        lifespan=lifespan,
    )

    if app_settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.cors_origin_list,
            allow_credentials=False,
            allow_methods=["GET", "OPTIONS"],
            allow_headers=["*"],
        )

    @app.exception_handler(SpatialApiError)
    async def spatial_error_handler(
        request: Request, exc: SpatialApiError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(psycopg.Error)
    async def database_error_handler(
        request: Request, exc: psycopg.Error
    ) -> JSONResponse:
        LOGGER.exception("Database error while handling %s", request.url.path)
        detail = "Database query failed."
        if app_settings.environment != "production":
            first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
            if first_line:
                detail = f"Database query failed: {first_line[:240]}"
        return JSONResponse(status_code=502, content={"detail": detail})

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "name": app_settings.app_name,
            "version": app_settings.app_version,
            "docs": "/docs",
            "health": f"{app_settings.api_prefix}/health",
        }

    app.include_router(health.router, prefix=app_settings.api_prefix)
    app.include_router(layers.router, prefix=app_settings.api_prefix)
    app.include_router(tiles.router, prefix=app_settings.api_prefix)

    return app


app = create_app()
