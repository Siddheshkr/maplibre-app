# Spatial Explorer

A fresh PostGIS → MapLibre application that renders vector layers **directly from the database**, with no GeoServer in the middle.

- MapLibre GL JS frontend (Angular, standalone)
- FastAPI + PostGIS backend
- Dynamic layer discovery from `geometry_columns`
- MVT vector tiles generated with `ST_AsMVT` / `ST_AsMVTGeom`
- Per-layer on/off toggles, opacity, search, and zoom-to-layer
- Click any feature to inspect its attributes
- Read-only API surface: no browser database credentials, no arbitrary SQL

## Architecture

```
┌──────────────────────┐        ┌──────────────────────────┐        ┌─────────────┐
│  Angular + MapLibre  │  HTTP  │  FastAPI spatial service │  SQL   │   PostGIS   │
│  browser             │ ─────► │  /api/layers             │ ─────► │  geometry   │
│                      │        │  /api/tiles/{layer}/…    │        │  tables     │
│  MapLibre renders    │ ◄───── │  /api/layers/{id}/features│ ◄───── │             │
│  MVT + GeoJSON       │        │                          │        │             │
└──────────────────────┘        └──────────────────────────┘        └─────────────┘
```

GeoServer is replaced by a small, purpose-built read-only API. The database stays on the server side; the browser only receives layer metadata, vector tiles, and feature JSON.

## Quick start

### 1. Demo database (optional)

Requires Docker.

```bash
docker compose up -d db
```

This starts PostGIS on `localhost:5432` with a demo dataset and a read-only user:

```text
database: gisdb
admin:    gis_admin / gis_admin
reader:   gis_reader / gis_reader
schemas:  gis, public
```

### 2. Backend

```bash
cd services/api
cp .env.example .env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for the API documentation, or check:

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/layers
```

### 3. Frontend

```bash
cd apps/web
npx -y npm@11 install
npx -y npm@11 start
```

Open `http://localhost:4200`. The dev server proxies `/api` to `http://127.0.0.1:8000`.

## Connecting your own PostGIS database

Edit `services/api/.env`:

```env
DATABASE_HOST=your-host
DATABASE_PORT=5432
DATABASE_NAME=your-database
DATABASE_USER=your_readonly_user
DATABASE_PASSWORD=your-password
DATABASE_SSLMODE=require
DATABASE_SCHEMAS=gis,public
```

Then restart the API. Layers are discovered automatically from PostGIS `geometry_columns`. Only the schemas listed in `DATABASE_SCHEMAS` are exposed.

Recommended database setup:

- Use a read-only role for the API.
- Every published table should have a **known SRID** (not `0`) and a **primary key**.
- Add a GiST index on every geometry column.
- Use `geometry`, not only `geography`, for published layers.
- Restrict visible columns with the `columns` allowlist in `config/layer_styles.json` when a table contains sensitive attributes.

See [docs/database-setup.md](docs/database-setup.md) for details.

## Layer configuration

`services/api/config/layer_styles.json` can override presentation per layer:

```json
{
  "layers": {
    "gis.parcels": {
      "title": "Land parcels",
      "visible": true,
      "minZoom": 12,
      "maxZoom": 22,
      "columns": ["id", "parcel_no", "status", "area_ha"],
      "style": {
        "fillColor": ["match", ["get", "status"],
          "vacant", "#f59e0b",
          "allotted", "#16a34a",
          "#64748b"],
        "fillOpacity": 0.42
      }
    }
  }
}
```

- `columns` is an allowlist. Anything not listed is excluded from tiles and popups.
- `visible`, `minZoom`, `maxZoom`, and `title` control the panel and map.
- Colors accept CSS strings or MapLibre expressions, so data-driven styling works without SLD.

Layers without an entry get sensible defaults derived from their geometry type.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | API + database status |
| `GET` | `/api/layers` | Discovered spatial layers |
| `GET` | `/api/layers/{schema}.{table}` | One layer definition |
| `GET` | `/api/layers/{schema}.{table}/extent` | Layer bounds in EPSG:4326 |
| `GET` | `/api/layers/{schema}.{table}/features` | GeoJSON features (bbox/limit/offset) |
| `GET` | `/api/layers/{schema}.{table}/features/{id}` | One feature |
| `GET` | `/api/tiles/{schema}.{table}/{z}/{x}/{y}.pbf` | MVT vector tile |

Full reference: [docs/api.md](docs/api.md). Architecture notes: [docs/architecture.md](docs/architecture.md).

## Project layout

```text
apps/web/                 Angular 21 + MapLibre GL JS
services/api/             FastAPI + psycopg + PostGIS
db/seed/                  Demo schema and layers
docs/                     Architecture, database, API docs
docker-compose.yml        Optional local PostGIS
Makefile                  Common commands
```

## Tests and builds

```bash
make test     # backend pytest + frontend Vitest
make build    # production Angular build
```

Or individually:

```bash
cd services/api && .venv/bin/pytest
cd apps/web && npx -y npm@11 test -- --watch=false
cd apps/web && npx -y npm@11 run build
```

## Basemap

The development basemap uses OpenStreetMap's public raster tiles. For production, set `basemapTilesUrl` in `apps/web/src/environments/environment.prod.ts` to your own tile provider, or configure `mapStyleUrl` with a complete MapLibre style. OSM's public tiles are not intended for high-traffic deployments.

## Security notes

- Database credentials live only in `services/api/.env`; they are never sent to the browser.
- The API is read-only and uses parameterised SQL plus identifier quoting.
- Layer ids are validated against a discovered registry; clients cannot request arbitrary tables.
- Restrict `DATABASE_SCHEMAS` and use a read-only database role.
- The `columns` allowlist in the style config keeps sensitive attributes out of tiles and popups.
- The API ships without authentication. Put it behind your existing auth/reverse proxy before exposing it publicly.
- The demo credentials are for local development only.

## Why not GeoServer?

GeoServer is a general-purpose WMS/WFS/SLD server. This app only needs vector data, so it uses PostGIS directly:

| GeoServer concern | Replacement here |
|---|---|
| WMS raster tiles of vectors | MVT vector tiles rendered by MapLibre |
| SLD styling | MapLibre style expressions |
| WFS / GetFeatureInfo | `/features` endpoints + `queryRenderedFeatures` |
| Workspace/layer registry | `geometry_columns` discovery + allowlisted schemas |
| GetLegendGraphic | Legend generated from the layer style |

This removes a large moving part and keeps styling and performance under application control. Raster/imagery serving is intentionally out of scope.
