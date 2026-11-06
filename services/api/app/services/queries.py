from __future__ import annotations

import psycopg
from psycopg import sql

from app.config import Settings
from app.errors import LayerNotFound, UnsupportedLayer
from app.models import LayerDefinition
from app.services.utils import is_integer_type


def _source_geometry(layer: LayerDefinition) -> sql.Composed:
    return sql.SQL("src.{}").format(sql.Identifier(layer.geometryColumn))


def _geometry_in(layer: LayerDefinition, srid: int) -> sql.Composed:
    source = _source_geometry(layer)
    if layer.srid == srid:
        return source
    return sql.SQL("ST_Transform({}, {})").format(source, sql.Literal(srid))


def _require_srid(layer: LayerDefinition) -> None:
    if layer.srid <= 0:
        raise UnsupportedLayer(
            f"Layer {layer.id} has no SRID. Register the geometry with "
            "ST_SetSRID/Find_SRID before publishing it."
        )


def _attribute_parts(layer: LayerDefinition) -> list[sql.Composed]:
    return [
        sql.SQL("src.{}").format(sql.Identifier(column))
        for column in layer.columns
    ]


async def fetch_tile(
    conn: psycopg.AsyncConnection,
    layer: LayerDefinition,
    z: int,
    x: int,
    y: int,
    settings: Settings,
) -> bytes:
    _require_srid(layer)

    select_parts = _attribute_parts(layer)
    uses_feature_id = bool(
        layer.featureIdColumn and is_integer_type(layer.featureIdType)
    )

    if (
        uses_feature_id
        and layer.featureIdColumn != "id"
        and "id" not in layer.columns
    ):
        select_parts.insert(
            0,
            sql.SQL("src.{} AS id").format(
                sql.Identifier(layer.featureIdColumn or "")
            ),
        )

    select_parts.append(
        sql.SQL(
            "ST_AsMVTGeom({}, bounds.geom, %(extent)s, %(buffer)s, true) AS geom"
        ).format(_geometry_in(layer, 3857))
    )

    feature_id_sql = (
        sql.Literal("id") if uses_feature_id else sql.SQL("NULL")
    )

    query = sql.SQL(
        """
        WITH bounds AS (
            SELECT ST_TileEnvelope(%(z)s, %(x)s, %(y)s) AS geom
        )
        SELECT ST_AsMVT(
            tile,
            %(mvt_layer)s,
            %(extent)s,
            'geom',
            {feature_id}
        ) AS mvt
        FROM (
            SELECT {select_columns}
            FROM {schema}.{table} AS src
            CROSS JOIN bounds
            WHERE {source_geom} IS NOT NULL
              AND {source_geom} && ST_Transform(bounds.geom, %(srid)s)
        ) AS tile
        WHERE tile.geom IS NOT NULL
        """
    ).format(
        feature_id=feature_id_sql,
        select_columns=sql.SQL(",\n                   ").join(select_parts),
        schema=sql.Identifier(layer.schemaName),
        table=sql.Identifier(layer.tableName),
        source_geom=_source_geometry(layer),
    )

    params = {
        "z": z,
        "x": x,
        "y": y,
        "extent": settings.tile_extent,
        "buffer": settings.tile_buffer,
        "srid": layer.srid,
        "mvt_layer": layer.tableName,
    }

    cursor = conn.cursor()
    await cursor.execute(query, params)
    row = await cursor.fetchone()
    if not row:
        return b""
    return bytes(row["mvt"] or b"")


async def fetch_features(
    conn: psycopg.AsyncConnection,
    layer: LayerDefinition,
    bbox: tuple[float, float, float, float] | None,
    limit: int,
    offset: int,
) -> list[dict]:
    _require_srid(layer)

    select_parts = _attribute_parts(layer)
    select_parts.append(
        sql.SQL("{} AS geom").format(_geometry_in(layer, 4326))
    )

    where_sql = sql.SQL("")
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if bbox is not None:
        params.update(
            {
                "min_x": bbox[0],
                "min_y": bbox[1],
                "max_x": bbox[2],
                "max_y": bbox[3],
            }
        )
        where_sql = sql.SQL(
            """
            WHERE ST_Intersects(
                {source_geom},
                ST_Transform(
                    ST_MakeEnvelope(
                        %(min_x)s, %(min_y)s, %(max_x)s, %(max_y)s, 4326
                    ),
                    %(srid)s
                )
            )
            """
        ).format(source_geom=_source_geometry(layer))

    row_query = sql.SQL(
        """
        SELECT {select_columns}
        FROM {schema}.{table} AS src
        {where_sql}
        LIMIT %(limit)s OFFSET %(offset)s
        """
    ).format(
        select_columns=sql.SQL(",\n               ").join(select_parts),
        schema=sql.Identifier(layer.schemaName),
        table=sql.Identifier(layer.tableName),
        where_sql=where_sql,
    )

    query = sql.SQL(
        """
        SELECT COALESCE(json_agg(feature), '[]'::json) AS features
        FROM (
            SELECT ST_AsGeoJSON(row_data, 'geom', 6)::json AS feature
            FROM ({row_query}) AS row_data
        ) AS features
        """
    ).format(row_query=row_query)
    params["srid"] = layer.srid

    cursor = conn.cursor()
    await cursor.execute(query, params)
    row = await cursor.fetchone()
    if not row:
        return []
    return row["features"] or []


async def fetch_extent(
    conn: psycopg.AsyncConnection, layer: LayerDefinition
) -> dict[str, float]:
    _require_srid(layer)

    query = sql.SQL(
        """
        SELECT
            ST_XMin(box) AS "minX",
            ST_YMin(box) AS "minY",
            ST_XMax(box) AS "maxX",
            ST_YMax(box) AS "maxY"
        FROM (
            SELECT ST_Extent({geom}) AS box
            FROM {schema}.{table} AS src
        ) AS extent_row
        """
    ).format(
        geom=_geometry_in(layer, 4326),
        schema=sql.Identifier(layer.schemaName),
        table=sql.Identifier(layer.tableName),
    )

    cursor = conn.cursor()
    await cursor.execute(query)
    row = await cursor.fetchone()
    if not row or row["minX"] is None:
        raise UnsupportedLayer(f"Layer {layer.id} has no geometry extent.")
    return {
        "minX": float(row["minX"]),
        "minY": float(row["minY"]),
        "maxX": float(row["maxX"]),
        "maxY": float(row["maxY"]),
    }


async def fetch_feature(
    conn: psycopg.AsyncConnection, layer: LayerDefinition, feature_id: str
) -> dict:
    _require_srid(layer)
    if not layer.featureIdColumn:
        raise UnsupportedLayer(
            f"Layer {layer.id} has no single-column primary key. "
            "Feature detail is unavailable."
        )

    property_parts: list[sql.Composable] = []
    for column in layer.columns:
        property_parts.append(sql.Literal(column))
        property_parts.append(
            sql.SQL("src.{}").format(sql.Identifier(column))
        )

    properties_sql = (
        sql.SQL("jsonb_build_object({})").format(
            sql.SQL(", ").join(property_parts)
        )
        if property_parts
        else sql.SQL("'{}'::jsonb")
    )

    query = sql.SQL(
        """
        SELECT
            ST_AsGeoJSON(ST_Transform({geom}, 4326))::json AS geometry,
            {properties} AS properties
        FROM {schema}.{table} AS src
        WHERE src.{feature_id_column}::text = %(feature_id)s
        LIMIT 1
        """
    ).format(
        geom=_source_geometry(layer),
        properties=properties_sql,
        schema=sql.Identifier(layer.schemaName),
        table=sql.Identifier(layer.tableName),
        feature_id_column=sql.Identifier(layer.featureIdColumn),
    )

    cursor = conn.cursor()
    await cursor.execute(query, {"feature_id": feature_id})
    row = await cursor.fetchone()
    if not row:
        raise LayerNotFound("Feature was not found.")
    return {
        "type": "Feature",
        "id": feature_id,
        "geometry": row["geometry"],
        "properties": row["properties"] or {},
    }
