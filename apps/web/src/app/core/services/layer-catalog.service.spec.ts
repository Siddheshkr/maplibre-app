import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { LayerDefinition } from '../models/layer.model';
import { LayerCatalogService } from './layer-catalog.service';

const LAYER: LayerDefinition = {
  id: 'gis.districts',
  schemaName: 'gis',
  tableName: 'districts',
  geometryColumn: 'geom',
  geometryType: 'Polygon',
  sourceGeometryType: 'MULTIPOLYGON',
  srid: 4326,
  title: 'Districts',
  defaultVisible: true,
  minZoom: 4,
  maxZoom: 16,
  featureIdColumn: 'id',
  featureIdType: 'integer',
  columnCount: 2,
  style: {
    fillColor: '#2563eb',
    fillOpacity: 0.3,
    lineColor: '#1d4ed8',
    lineWidth: 1.2,
    lineOpacity: 1,
    circleColor: '#2563eb',
    circleRadius: 5.5,
    circleStrokeColor: '#ffffff',
    circleStrokeWidth: 1.5,
    circleOpacity: 1,
  },
};

describe('LayerCatalogService', () => {
  let service: LayerCatalogService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });

    service = TestBed.inject(LayerCatalogService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('loads the layer catalogue', () => {
    service.load();

    http.expectOne('/api/layers').flush({
      layers: [LAYER],
      generatedAt: '2026-01-01T00:00:00Z',
    });

    expect(service.status()).toBe('ready');
    expect(service.layers()).toEqual([LAYER]);
    expect(service.layerCount()).toBe(1);
  });

  it('distinguishes an unconfigured database from a generic error', () => {
    service.load();

    http.expectOne('/api/layers').flush(
      { detail: 'Database is not configured. Set DATABASE_* values.' },
      { status: 503, statusText: 'Service Unavailable' },
    );

    expect(service.status()).toBe('unconfigured');
    expect(service.layers()).toEqual([]);
  });

  it('reports an unreachable API', () => {
    service.load();

    http
      .expectOne('/api/layers')
      .error(new ProgressEvent('error'), { status: 0, statusText: 'Unknown' });

    expect(service.status()).toBe('error');
    expect(service.error()).toContain('unreachable');
  });
});
