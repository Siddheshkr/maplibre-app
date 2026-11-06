# Architecture

## Goal

Render vector layers stored in PostGIS on a MapLibre map, with layer visibility controls, without GeoServer.

## Non-goals

- Raster/imagery tile serving (COG, WMS, WMTS)
- Authoring or publishing workflows
- User management / authentication (the API is designed to be placed behind an existing auth layer)
- Editing features from the map

## Components

### Frontend — `apps/web`

Angular 21 standalone application.

- `MapViewComponent` owns the MapLibre map, vector sources, render layers, popups, and extent fitting.
- `LayerPanelComponent` renders the catalogue, toggles, opacity controls, search, and zoom-to-layer.
- `LayerCatalogService` loads `/api/layers` and `/api/layers/{id}/extent`.
- `App` owns the visibility/opacity state with Angular linked signals.

Each API layer becomes one MapLibre vector source. Polygon layers add fill + outline render layers; line layers add one line layer; point layers add one circle layer. `Unknown` geometry tables get all three and MapLibre ignores geometries that do not match.

### Backend — `services/api`

FastAPI service with a psycopg async connection pool.

- `SpatialRegistry` discovers tables from PostGIS `geometry_columns`, joins column metadata and primary keys, applies the style/column configuration, and caches the result.
- `queries.py` builds all SQL. Identifiers are quoted with `psycopg.sql.Identifier`; values are parameterised.
- Routers expose health, catalogue, extent, feature, and tile endpoints.
- `Database` is lazy: the API starts even if the database is down, and `/api/health` reports `not_configured` / `unavailable`.

### Database

The only supported source is PostGIS geometry columns. Geography-only tables are currently ignored.

## Request flows

### Layer catalogue

```
GET /api/layers
  → SpatialRegistry.list_layers()
  → SELECT ... FROM geometry_columns
  → information_schema.columns (attributes)
  → information_schema.table_constraints (primary key)
  → merge config/layer_styles.json
  → cache for LAYER_CACHE_TTL_SECONDS
```

### Vector tiles

```
GET /api/tiles/gis.parcels/12/2850/1750.pbf
  → validate layer id against registry
  → validate z/x/y
  → ST_TileEnvelope(12, 2850, 1750)
  → bbox filter with the layer's GiST index
  → ST_AsMVTGeom(..., 3857)
  → ST_AsMVT(...)
```

The tile endpoint returns `application/vnd.mapbox-vector-tile`. MapLibre requests tiles only for the current viewport and zoom.

### Feature inspection

Map clicks use `map.queryRenderedFeatures()` against already-loaded tiles. No network request is needed for the popup. The `/features` endpoints exist for full attribute access, exports, and server-side queries by bbox.

### Zoom to layer

```
GET /api/layers/gis.parcels/extent
  → ST_Extent(ST_Transform(geom, 4326))
  → map.fitBounds(...)
```

Extent is calculated on demand rather than on catalogue load so large tables do not slow startup.

## Security model

- The browser never receives database credentials.
- The API is read-only (`SELECT` only).
- Layer identifiers must match `schema.table` and exist in the discovered registry.
- Schema and table names are always quoted as identifiers; values are parameterised.
- `DATABASE_SCHEMAS` limits discovery to approved schemas.
- `columns` allowlists in `layer_styles.json` limit which attributes are returned.
- `statement_timeout` bounds every query.
- `MAX_FEATURES` bounds GeoJSON responses.
- CORS is restricted to configured origins.

For production, also:

- put the API behind your existing authentication/authorization layer;
- use a database role that only has `CONNECT`, `USAGE` on approved schemas, and `SELECT`;
- serve the Angular build and reverse-proxy `/api` from the same origin;
- keep `.env` out of version control.

## Performance notes

- MVT is efficient for large layers because MapLibre renders on the GPU and only fetches viewport tiles.
- Every published geometry column should have a GiST index.
- Low-zoom tiles can be simplified. Add a materialised view with `ST_SimplifyPreserveTopology` if a layer is very detailed and widely viewed.
- The catalogue cache avoids metadata queries on every page load.
- Tile responses carry `Cache-Control: public, max-age=60`; place a CDN or reverse-proxy cache in front for production.
- `ST_AsMVTGeom` clips to the tile; `&&` on the source geometry uses the spatial index.

## Extension points

- Add JWT/permission middleware and filter discovered layers per user.
- Add a materialised-view registry for curated, pre-simplified layers.
- Add a `/search` endpoint for attribute search.
- Add server-side style presets per user/role.
- Add a Cesium or MapLibre 3D view for the same MVT sources.

## Known limitations

- One geometry column per table (the first returned by `geometry_columns`).
- Geometry SRID must be known and greater than 0.
- Geography columns are not discovered yet.
- Composite primary keys do not get a single-feature detail route.
- No attribute filtering UI yet; the `/features` endpoint accepts bbox and pagination.
- No raster support by design.
