# API reference

Base path: `/api`

All responses are JSON except vector tiles.

## Errors

```json
{
  "detail": "Layer was not found or is not published."
}
```

| Status | Meaning |
|---|---|
| `400` | Invalid layer id, bbox, or tile coordinates |
| `404` | Layer/feature not found |
| `422` | Layer cannot be served (unknown SRID, no extent, no primary key) |
| `502` | Database query failed |
| `503` | Database not configured or unavailable |

## Health

```http
GET /api/health
```

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "development",
  "database": "connected",
  "schemas": ["gis", "public"]
}
```

`database` is one of `connected`, `not_configured`, `unavailable`.

## List layers

```http
GET /api/layers
GET /api/layers?refresh=true
```

```json
{
  "layers": [
    {
      "id": "gis.districts",
      "schemaName": "gis",
      "tableName": "districts",
      "geometryColumn": "geom",
      "geometryType": "Polygon",
      "sourceGeometryType": "MULTIPOLYGON",
      "srid": 4326,
      "title": "Districts",
      "defaultVisible": true,
      "minZoom": 4,
      "maxZoom": 16,
      "featureIdColumn": "id",
      "featureIdType": "integer",
      "columnCount": 2,
      "style": {
        "fillColor": "#2563eb",
        "fillOpacity": 0.28,
        "lineColor": "#1d4ed8",
        "lineWidth": 1.4
      }
    }
  ],
  "generatedAt": "2026-11-06T06:00:00Z"
}
```

`refresh=true` bypasses the registry cache.

## One layer

```http
GET /api/layers/gis.districts
```

Returns a single layer definition.

## Extent

```http
GET /api/layers/gis.districts/extent
```

```json
{
  "minX": 91.10,
  "minY": 23.28,
  "maxX": 92.08,
  "maxY": 24.22
}
```

Returns EPSG:4326 bounds.

## Features

```http
GET /api/layers/gis.parcels/features
GET /api/layers/gis.parcels/features?bbox=91.45,23.65,91.75,23.90&limit=250&offset=0
```

| Parameter | Default | Description |
|---|---|---|
| `bbox` | none | `minLng,minLat,maxLng,maxLat` in EPSG:4326 |
| `limit` | `DEFAULT_FEATURE_LIMIT` (500) | Maximum `MAX_FEATURES` (2000) |
| `offset` | 0 | Pagination offset |

Response is a GeoJSON FeatureCollection. Geometry is always EPSG:4326.

## One feature

```http
GET /api/layers/gis.parcels/features/42
```

```json
{
  "type": "Feature",
  "id": "42",
  "geometry": { "type": "Polygon", "coordinates": [[...]] },
  "properties": {
    "id": 42,
    "parcel_no": "P-042",
    "status": "allotted",
    "area_ha": 0.42
  }
}
```

Requires a single-column primary key or a column named `id`.

## Vector tiles

```http
GET /api/tiles/gis.parcels/{z}/{x}/{y}.pbf
```

Example MapLibre source:

```ts
map.addSource('gis.parcels', {
  type: 'vector',
  tiles: ['/api/tiles/gis.parcels/{z}/{x}/{y}.pbf'],
  minzoom: 12,
  maxzoom: 22,
});

map.addLayer({
  id: 'gis.parcels--fill',
  type: 'fill',
  source: 'gis.parcels',
  'source-layer': 'parcels',
  paint: {
    'fill-color': [
      'match',
      ['get', 'status'],
      'vacant',
      '#f59e0b',
      'allotted',
      '#16a34a',
      '#64748b',
    ],
    'fill-opacity': 0.42,
  },
});
```

Notes:

- The MVT layer name is the database table name (`parcels`), not the full `schema.table` id.
- If the table has an integer primary key, it is emitted as the MVT feature id.
- The endpoint returns an empty body for tiles with no features; MapLibre handles this normally.
- Tiles are limited to zoom 0–22.

## Interactive documentation

FastAPI serves OpenAPI docs at `/docs` and the schema at `/openapi.json` when the service is running.
