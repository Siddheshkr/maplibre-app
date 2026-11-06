from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import psycopg
from psycopg import sql

from app.config import Settings
from app.database import Database
from app.errors import DatabaseNotConfigured, LayerNotFound, UnsupportedLayer
from app.models import LayerDefinition, LayerStyle
from app.services.utils import (
    humanize_identifier,
    normalize_geometry_type,
    validate_layer_id,
)

LOGGER = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]

PALETTE = [
    "#2563eb",
    "#0d9488",
    "#d97706",
    "#7c3aed",
    "#dc2626",
    "#0891b2",
    "#65a30d",
    "#db2777",
]

SCALAR_SKIP_TYPES = {"bytea", "array"}
SCALAR_SKIP_UDTS = {"geometry", "geography", "bytea"}


class SpatialRegistry:
    """Discovers approved PostGIS tables and turns them into layer definitions."""

    def __init__(self, settings: Settings, database: Database) -> None:
        self._settings = settings
        self._database = database
        self._cached_layers: list[LayerDefinition] = []
        self._cached_at = 0.0
        self._lock = asyncio.Lock()

    async def list_layers(self, force: bool = False) -> list[LayerDefinition]:
        ttl = self._settings.layer_cache_ttl_seconds
        if (
            not force
            and self._cached_at
            and (time.monotonic() - self._cached_at) < ttl
        ):
            return self._cached_layers

        async with self._lock:
            if (
                not force
                and self._cached_at
                and (time.monotonic() - self._cached_at) < ttl
            ):
                return self._cached_layers

            self._cached_layers = await self._load_layers()
            self._cached_at = time.monotonic()
            return self._cached_layers

    async def get_layer(self, layer_id: str) -> LayerDefinition:
        validate_layer_id(layer_id)
        layers = await self.list_layers()
        for layer in layers:
            if layer.id == layer_id:
                return layer
        raise LayerNotFound()

    def invalidate(self) -> None:
        self._cached_at = 0.0

    async def _load_layers(self) -> list[LayerDefinition]:
        if not self._database.configured:
            raise DatabaseNotConfigured()

        style_config = self._load_style_config()
        schemas = self._settings.schemas
        if not schemas:
            return []

        try:
            async with self._database.connection() as conn:
                geometry_rows = await self._fetch_geometry_columns(conn, schemas)
                column_rows = await self._fetch_columns(conn, schemas)
                primary_keys = await self._fetch_primary_keys(conn, schemas)
        except psycopg.errors.UndefinedTable as exc:
            raise UnsupportedLayer(
                "PostGIS metadata was not found. Enable the PostGIS extension "
                "and make sure the configured schemas contain spatial tables."
            ) from exc

        columns_by_table: dict[tuple[str, str], list[dict]] = {}
        for row in column_rows:
            key = (row["table_schema"], row["table_name"])
            columns_by_table.setdefault(key, []).append(row)

        layers: list[LayerDefinition] = []
        seen_tables: set[tuple[str, str]] = set()

        for index, row in enumerate(geometry_rows):
            key = (row["f_table_schema"], row["f_table_name"])
            if key in seen_tables:
                # Only the first geometry column of a table is published.
                continue
            seen_tables.add(key)

            layer_id = f"{key[0]}.{key[1]}"
            config = style_config.get(layer_id, {})
            if not isinstance(config, dict):
                config = {}

            geometry_type = normalize_geometry_type(row["type"])
            color = PALETTE[index % len(PALETTE)]
            style = self._build_style(geometry_type, color, config.get("style"))
            attributes = self._select_attributes(
                columns_by_table.get(key, []),
                row["f_geometry_column"],
                config.get("columns"),
            )
            attribute_names = [column["column_name"] for column in attributes]
            attribute_lookup = {
                column["column_name"]: column for column in attributes
            }

            primary_key_columns = primary_keys.get(key, [])
            primary_key = (
                primary_key_columns[0] if len(primary_key_columns) == 1 else None
            )
            if primary_key and primary_key in attribute_lookup:
                feature_id_column = primary_key
            elif "id" in attribute_lookup:
                feature_id_column = "id"
            else:
                feature_id_column = None

            feature_id_type = None
            if feature_id_column:
                feature_id_type = attribute_lookup[feature_id_column].get("data_type")

            title = config.get("title")
            if not isinstance(title, str) or not title.strip():
                title = humanize_identifier(key[1])

            visible = config.get("visible")
            if not isinstance(visible, bool):
                visible = index < self._settings.default_visible_layers

            min_zoom = self._int_setting(config.get("minZoom"), 0, 0, 22)
            max_zoom = self._int_setting(config.get("maxZoom"), 22, min_zoom, 24)

            layers.append(
                LayerDefinition(
                    id=layer_id,
                    schemaName=key[0],
                    tableName=key[1],
                    geometryColumn=row["f_geometry_column"],
                    geometryType=geometry_type,  # type: ignore[arg-type]
                    sourceGeometryType=str(row["type"] or "GEOMETRY"),
                    srid=int(row["srid"] or 0),
                    title=title.strip(),
                    defaultVisible=visible,
                    minZoom=min_zoom,
                    maxZoom=max_zoom,
                    featureIdColumn=feature_id_column,
                    featureIdType=feature_id_type,
                    columnCount=len(attribute_names),
                    style=style,
                    columns=attribute_names,
                )
            )

        return layers

    async def _fetch_geometry_columns(
        self, conn: psycopg.AsyncConnection, schemas: list[str]
    ) -> list[dict]:
        query = sql.SQL(
            """
            SELECT f_table_schema, f_table_name, f_geometry_column, srid, type
            FROM geometry_columns
            WHERE f_table_schema = ANY(%s)
            ORDER BY f_table_schema, f_table_name, f_geometry_column
            """
        )
        cursor = await conn.execute(query, (schemas,))
        return await cursor.fetchall()

    async def _fetch_columns(
        self, conn: psycopg.AsyncConnection, schemas: list[str]
    ) -> list[dict]:
        query = sql.SQL(
            """
            SELECT table_schema, table_name, column_name, data_type, udt_name,
                   ordinal_position
            FROM information_schema.columns
            WHERE table_schema = ANY(%s)
            ORDER BY table_schema, table_name, ordinal_position
            """
        )
        cursor = await conn.execute(query, (schemas,))
        return await cursor.fetchall()

    async def _fetch_primary_keys(
        self, conn: psycopg.AsyncConnection, schemas: list[str]
    ) -> dict[tuple[str, str], list[str]]:
        query = sql.SQL(
            """
            SELECT tc.table_schema, tc.table_name, kcu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
             AND tc.table_name = kcu.table_name
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = ANY(%s)
            ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
            """
        )
        cursor = await conn.execute(query, (schemas,))
        result: dict[tuple[str, str], list[str]] = {}
        for row in await cursor.fetchall():
            key = (row["table_schema"], row["table_name"])
            result.setdefault(key, []).append(row["column_name"])
        return result

    def _select_attributes(
        self,
        columns: list[dict],
        geometry_column: str,
        allowlist: object,
    ) -> list[dict]:
        allowed: set[str] | None = None
        if isinstance(allowlist, list):
            allowed = {item for item in allowlist if isinstance(item, str)}

        selected: list[dict] = []
        for column in columns:
            name = column["column_name"]
            data_type = (column.get("data_type") or "").lower()
            udt_name = (column.get("udt_name") or "").lower()

            if name == geometry_column:
                continue
            if data_type in SCALAR_SKIP_TYPES or udt_name in SCALAR_SKIP_UDTS:
                continue
            if allowed is not None and name not in allowed:
                continue
            selected.append(column)

        return selected[: self._settings.max_columns]

    def _build_style(
        self, geometry_type: str, color: str, overrides: object
    ) -> LayerStyle:
        style = LayerStyle()

        if geometry_type == "Polygon":
            style.fillColor = color
            style.fillOpacity = 0.35
            style.lineColor = color
            style.lineWidth = 1.1
        elif geometry_type == "LineString":
            style.lineColor = color
            style.lineWidth = 2.25
        elif geometry_type == "Point":
            style.circleColor = color
            style.circleRadius = 5.5
        else:
            style.fillColor = color
            style.fillOpacity = 0.3
            style.lineColor = color
            style.lineWidth = 1.4
            style.circleColor = color

        if isinstance(overrides, dict):
            style = LayerStyle.model_validate(
                {**style.model_dump(), **overrides}
            )
        return style

    def _load_style_config(self) -> dict:
        path = Path(self._settings.style_config_path)
        if not path.is_absolute():
            path = BASE_DIR / path

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Could not read layer style config %s: %s", path, exc)
            return {}

        if not isinstance(raw, dict):
            return {}
        layers = raw.get("layers")
        if isinstance(layers, dict):
            return layers
        return raw

    @staticmethod
    def _int_setting(value: object, default: int, low: int, high: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            return default
        return max(low, min(high, value))
