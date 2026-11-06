from __future__ import annotations


class SpatialApiError(Exception):
    """Base class for errors that are safe to return to API clients."""

    status_code = 400
    default_detail = "Spatial request failed."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class DatabaseNotConfigured(SpatialApiError):
    status_code = 503
    default_detail = (
        "Database is not configured. Set DATABASE_* values in services/api/.env."
    )


class DatabaseUnavailable(SpatialApiError):
    status_code = 503
    default_detail = "The spatial database is unavailable."


class InvalidLayerId(SpatialApiError):
    status_code = 400
    default_detail = "Layer id must use the form schema.table."


class LayerNotFound(SpatialApiError):
    status_code = 404
    default_detail = "Layer was not found or is not published."


class UnsupportedLayer(SpatialApiError):
    status_code = 422
    default_detail = "This layer cannot be served with the current configuration."


class InvalidBoundingBox(SpatialApiError):
    status_code = 400
    default_detail = "bbox must be minLng,minLat,maxLng,maxLat."


class InvalidTileCoordinates(SpatialApiError):
    status_code = 400
    default_detail = "Tile coordinates are outside the supported range."
