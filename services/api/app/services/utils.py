from __future__ import annotations

import re

from app.errors import InvalidBoundingBox, InvalidLayerId, InvalidTileCoordinates

LAYER_ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")

INTEGER_TYPES = {"smallint", "integer", "bigint", "int2", "int4", "int8"}


def validate_layer_id(layer_id: str) -> tuple[str, str]:
    if not LAYER_ID_PATTERN.fullmatch(layer_id or ""):
        raise InvalidLayerId("Layer id must use the form schema.table.")
    schema_name, table_name = layer_id.split(".", 1)
    return schema_name, table_name


def humanize_identifier(value: str) -> str:
    cleaned = value.replace("_", " ").strip()
    if not cleaned:
        return value
    return cleaned[0].upper() + cleaned[1:]


def normalize_geometry_type(value: str | None) -> str:
    raw = (value or "").upper()
    if "POLYGON" in raw:
        return "Polygon"
    if "LINE" in raw:
        return "LineString"
    if "POINT" in raw:
        return "Point"
    return "Unknown"


def is_integer_type(value: str | None) -> bool:
    return (value or "").lower() in INTEGER_TYPES


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None or not value.strip():
        return None

    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise InvalidBoundingBox()

    try:
        min_x, min_y, max_x, max_y = (float(part) for part in parts)
    except ValueError as exc:
        raise InvalidBoundingBox() from exc

    if not (-180 <= min_x <= 180 and -180 <= max_x <= 180):
        raise InvalidBoundingBox("bbox longitudes must be between -180 and 180.")
    if not (-90 <= min_y <= 90 and -90 <= max_y <= 90):
        raise InvalidBoundingBox("bbox latitudes must be between -90 and 90.")
    if min_x >= max_x or min_y >= max_y:
        raise InvalidBoundingBox("bbox must be ordered minLng,minLat,maxLng,maxLat.")

    return min_x, min_y, max_x, max_y


def validate_tile_coordinates(z: int, x: int, y: int) -> None:
    if z < 0 or z > 22:
        raise InvalidTileCoordinates("Tile zoom must be between 0 and 22.")
    limit = 1 << z
    if not (0 <= x < limit and 0 <= y < limit):
        raise InvalidTileCoordinates()
