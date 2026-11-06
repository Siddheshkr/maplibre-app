from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, Response

from app.config import Settings
from app.database import Database
from app.errors import UnsupportedLayer
from app.models import LayerDefinition, LayerExtent, LayersResponse
from app.services.queries import fetch_extent, fetch_feature, fetch_features
from app.services.registry import SpatialRegistry
from app.services.utils import parse_bbox, validate_layer_id

router = APIRouter(prefix="/layers", tags=["layers"])


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_registry(request: Request) -> SpatialRegistry:
    return request.app.state.registry


def get_database(request: Request) -> Database:
    return request.app.state.database


@router.get("", response_model=LayersResponse)
async def list_layers(
    request: Request,
    refresh: bool = Query(False),
    registry: SpatialRegistry = Depends(get_registry),
) -> LayersResponse:
    layers = await registry.list_layers(force=refresh)
    return LayersResponse(
        layers=layers,
        generatedAt=datetime.now(timezone.utc),
    )


@router.get("/{layer_id}", response_model=LayerDefinition)
async def get_layer(
    layer_id: str,
    registry: SpatialRegistry = Depends(get_registry),
) -> LayerDefinition:
    return await registry.get_layer(layer_id)


@router.get("/{layer_id}/extent", response_model=LayerExtent)
async def get_layer_extent(
    layer_id: str,
    registry: SpatialRegistry = Depends(get_registry),
    database: Database = Depends(get_database),
) -> LayerExtent:
    validate_layer_id(layer_id)
    layer = await registry.get_layer(layer_id)
    async with database.connection() as conn:
        extent = await fetch_extent(conn, layer)
    return LayerExtent(**extent)


@router.get("/{layer_id}/features")
async def get_layer_features(
    layer_id: str,
    bbox: str | None = Query(
        None,
        description="minLng,minLat,maxLng,maxLat in EPSG:4326",
    ),
    limit: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0),
    registry: SpatialRegistry = Depends(get_registry),
    database: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> dict:
    validate_layer_id(layer_id)
    layer = await registry.get_layer(layer_id)
    parsed_bbox = parse_bbox(bbox)

    effective_limit = limit or settings.default_feature_limit
    if effective_limit > settings.max_features:
        raise UnsupportedLayer(
            f"limit exceeds the server maximum of {settings.max_features}."
        )

    async with database.connection() as conn:
        features = await fetch_features(
            conn, layer, parsed_bbox, effective_limit, offset
        )
    return {"type": "FeatureCollection", "features": features}


@router.get("/{layer_id}/features/{feature_id}")
async def get_layer_feature(
    layer_id: str,
    feature_id: str,
    registry: SpatialRegistry = Depends(get_registry),
    database: Database = Depends(get_database),
) -> dict:
    validate_layer_id(layer_id)
    layer = await registry.get_layer(layer_id)
    async with database.connection() as conn:
        return await fetch_feature(conn, layer, feature_id)
