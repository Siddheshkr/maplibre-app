from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

GeometryType = Literal["Point", "LineString", "Polygon", "Unknown"]

# Colours may be a plain CSS hex string or a MapLibre expression array.
ColorValue = str | list[Any] | dict[str, Any]


class LayerStyle(BaseModel):
    """MapLibre-friendly style values for a published layer."""

    fillColor: ColorValue = "#2563eb"
    fillOpacity: float = 0.35
    lineColor: ColorValue = "#1d4ed8"
    lineWidth: float = 1.2
    lineOpacity: float = 1.0
    circleColor: ColorValue = "#2563eb"
    circleRadius: float = 5.5
    circleStrokeColor: ColorValue = "#ffffff"
    circleStrokeWidth: float = 1.5
    circleOpacity: float = 1.0


class LayerDefinition(BaseModel):
    id: str
    schemaName: str
    tableName: str
    geometryColumn: str
    geometryType: GeometryType
    sourceGeometryType: str
    srid: int
    title: str
    defaultVisible: bool
    minZoom: int = 0
    maxZoom: int = 22
    featureIdColumn: str | None = None
    featureIdType: str | None = None
    columnCount: int = 0
    style: LayerStyle
    columns: list[str] = Field(default_factory=list, exclude=True)


class LayersResponse(BaseModel):
    layers: list[LayerDefinition]
    generatedAt: datetime


class LayerExtent(BaseModel):
    minX: float
    minY: float
    maxX: float
    maxY: float


class FeatureDetail(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str | int | None = None
    geometry: dict | None = None
    properties: dict


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict]
