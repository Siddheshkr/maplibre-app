# Database setup

## Option A — demo PostGIS with Docker

```bash
docker compose up -d db
```

The container runs `db/seed/001_sample_layers.sql` on first start and creates the `gis` schema with four layers:

| Layer | Geometry | Attributes |
|---|---|---|
| `gis.districts` | MultiPolygon | name, state |
| `gis.roads` | LineString | name, road_class |
| `gis.facilities` | Point | name, category |
| `gis.parcels` | Polygon | parcel_no, status, area_ha |

Credentials:

```text
database: gisdb
admin:    gis_admin / gis_admin
reader:   gis_reader / gis_reader
```

To reset the demo database:

```bash
docker compose down -v
docker compose up -d db
```

## Option B — your existing PostGIS database

1. Create a dedicated read-only role:

```sql
CREATE ROLE gis_reader LOGIN PASSWORD 'replace-me';
GRANT CONNECT ON DATABASE your_database TO gis_reader;
GRANT USAGE ON SCHEMA gis TO gis_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA gis TO gis_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA gis
  GRANT SELECT ON TABLES TO gis_reader;
```

2. Configure `services/api/.env`:

```env
DATABASE_HOST=db.example.com
DATABASE_PORT=5432
DATABASE_NAME=your_database
DATABASE_USER=gis_reader
DATABASE_PASSWORD=replace-me
DATABASE_SSLMODE=require
DATABASE_SCHEMAS=gis,public
```

3. Restart the API and check:

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/layers
```

## Requirements for a published layer

### Known SRID

The API reads `srid` from `geometry_columns`. A value of `0` is rejected by the tile and feature endpoints.

Check:

```sql
SELECT f_table_schema, f_table_name, f_geometry_column, srid, type
FROM geometry_columns
WHERE f_table_schema = 'gis';
```

Fix an unknown SRID:

```sql
ALTER TABLE gis.my_table
  ALTER COLUMN geom TYPE geometry(Point, 4326)
  USING ST_SetSRID(geom, 4326);
```

For views, create them with an explicit geometry type and SRID so PostGIS can register them:

```sql
CREATE VIEW gis.published_plots AS
SELECT id, name, status, geom::geometry(Polygon, 4326) AS geom
FROM gis.plots;
```

### Primary key

A single-column primary key enables popups with a stable feature id and the `/features/{id}` route. Tables without a key still render; only feature detail is unavailable.

### GiST index

```sql
CREATE INDEX IF NOT EXISTS my_table_geom_idx
  ON gis.my_table USING GIST (geom);
```

Without an index, tile requests can become full-table scans.

### Attribute columns

The API publishes scalar columns automatically, up to `MAX_COLUMNS` (default 40). Arrays and `bytea` are skipped.

Use a `columns` allowlist in `services/api/config/layer_styles.json` to hide sensitive attributes:

```json
{
  "layers": {
    "gis.people": {
      "columns": ["id", "full_name", "district"]
    }
  }
}
```

Only those columns are selected into tiles and popups.

## Style configuration reference

Path: `services/api/config/layer_styles.json`.

```json
{
  "layers": {
    "schema.table": {
      "title": "Display name",
      "visible": true,
      "minZoom": 4,
      "maxZoom": 22,
      "columns": ["id", "name"],
      "style": {
        "fillColor": "#2563eb",
        "fillOpacity": 0.35,
        "lineColor": "#1d4ed8",
        "lineWidth": 1.2,
        "lineOpacity": 1.0,
        "circleColor": "#2563eb",
        "circleRadius": 5.5,
        "circleStrokeColor": "#ffffff",
        "circleStrokeWidth": 1.5,
        "circleOpacity": 1.0
      }
    }
  }
}
```

Colours accept MapLibre expressions:

```json
{
  "fillColor": [
    "match",
    ["get", "status"],
    "vacant", "#f59e0b",
    "allotted", "#16a34a",
    "#64748b"
  ]
}
```

Defaults:

- `visible`: every discovered layer is visible by default. Set `DEFAULT_VISIBLE_LAYERS` to limit the initial set, or set `visible` per layer.
- `minZoom` / `maxZoom`: 0 / 22.
- `title`: humanised table name.
- Style: colour from the layer palette, based on geometry type.

Changes are picked up after `LAYER_CACHE_TTL_SECONDS` (default 60) or immediately with `GET /api/layers?refresh=true`.

## Views and materialised views

PostGIS registers geometry columns on views and materialised views, so both are discoverable. For large or complex layers, publish a materialised view with simplified geometry:

```sql
CREATE MATERIALIZED VIEW gis.roads_simplified AS
SELECT id, name, road_class,
       ST_SimplifyPreserveTopology(geom, 0.00005)::geometry(LineString, 4326) AS geom
FROM gis.roads;

CREATE UNIQUE INDEX ON gis.roads_simplified (id);
CREATE INDEX ON gis.roads_simplified USING GIST (geom);
```

Refresh it on your own schedule with `REFRESH MATERIALIZED VIEW CONCURRENTLY`.

## Troubleshooting

| Symptom | Check |
|---|---|
| `/api/layers` returns 503 "not configured" | `services/api/.env` exists and the API was restarted |
| Layer list is empty | `DATABASE_SCHEMAS` matches the schema that owns the tables; tables appear in `geometry_columns` |
| Tile requests return 422 | Layer SRID is `0` or the geometry is invalid |
| Tiles are empty | Verify the table has rows in the current viewport; check the tile URL and `source-layer` |
| Popup has no attributes | The `columns` allowlist excluded them, or the table has no scalar columns |
| Slow first paint | Add GiST indexes and limit visible layers / max zoom |
