from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from app.config import Settings
from app.database import Database
from app.services.queries import fetch_tile
from app.services.registry import SpatialRegistry
from app.services.utils import validate_layer_id, validate_tile_coordinates

router = APIRouter(prefix="/tiles", tags=["tiles"])


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_registry(request: Request) -> SpatialRegistry:
    return request.app.state.registry


def get_database(request: Request) -> Database:
    return request.app.state.database


@router.get("/{layer_id}/{z}/{x}/{y}.pbf")
async def get_vector_tile(
    layer_id: str,
    z: int,
    x: int,
    y: int,
    registry: SpatialRegistry = Depends(get_registry),
    database: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> Response:
    validate_layer_id(layer_id)
    validate_tile_coordinates(z, x, y)
    layer = await registry.get_layer(layer_id)

    async with database.connection() as conn:
        payload = await fetch_tile(conn, layer, z, x, y, settings)

    return Response(
        content=payload,
        media_type="application/vnd.mapbox-vector-tile",
        headers={
            "Cache-Control": "public, max-age=60",
            "X-Layer-Id": layer.id,
        },
    )
