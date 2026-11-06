import {
  AfterViewInit,
  Component,
  ElementRef,
  OnDestroy,
  effect,
  inject,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import * as maplibregl from 'maplibre-gl';
import type {
  LayerSpecification,
  Map as MapLibreMap,
  MapMouseEvent,
  Popup as MapLibrePopup,
  StyleSpecification,
} from 'maplibre-gl';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import { LayerDefinition } from '../../core/models/layer.model';
import { LayerCatalogService } from '../../core/services/layer-catalog.service';

interface ManagedLayer {
  definition: LayerDefinition;
  renderIds: string[];
}

@Component({
  selector: 'app-map-view',
  templateUrl: './map-view.component.html',
  styleUrl: './map-view.component.scss',
})
export class MapViewComponent implements AfterViewInit, OnDestroy {
  private readonly catalog = inject(LayerCatalogService);
  private readonly mapContainer =
    viewChild.required<ElementRef<HTMLDivElement>>('mapContainer');

  readonly layers = input.required<readonly LayerDefinition[]>();
  readonly visibility = input.required<Record<string, boolean>>();
  readonly opacity = input.required<Record<string, number>>();

  readonly notice = signal<string | null>(null);
  private readonly ready = signal(false);

  private map?: MapLibreMap;
  private popup?: MapLibrePopup;
  private resizeObserver?: ResizeObserver;
  private noticeTimer?: number;
  private lastHoverCheck = 0;

  private readonly managed = new Map<string, ManagedLayer>();
  private readonly renderToLayer = new Map<string, LayerDefinition>();

  constructor() {
    effect(() => {
      const ready = this.ready();
      const layers = this.layers();
      if (!ready || !this.map) {
        return;
      }

      const visibility = untracked(() => this.visibility());
      const opacity = untracked(() => this.opacity());
      this.rebuildLayers(layers, visibility, opacity);
    });

    effect(() => {
      const ready = this.ready();
      const visibility = this.visibility();
      if (!ready || !this.map) {
        return;
      }
      this.applyVisibility(visibility);
    });

    effect(() => {
      const ready = this.ready();
      const opacity = this.opacity();
      if (!ready || !this.map) {
        return;
      }
      this.applyOpacity(opacity);
    });
  }

  ngAfterViewInit(): void {
    const container = this.mapContainer().nativeElement;

    // Angular's dev server pre-bundles maplibre-gl, so the worker URL cannot be
    // inferred from import.meta.url. The worker is copied from the package by
    // the asset configuration in angular.json.
    maplibregl.setWorkerUrl(
      new URL('maplibre-gl-worker.mjs', document.baseURI).href,
    );

    const map = new maplibregl.Map({
      container,
      style: this.baseStyle(),
      center: environment.initialCenter,
      zoom: environment.initialZoom,
      maxZoom: environment.maxZoom,
      attributionControl: false,
    });
    this.map = map;

    map.addControl(
      new maplibregl.NavigationControl({ showCompass: true }),
      'top-right',
    );
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    map.addControl(
      new maplibregl.AttributionControl({ compact: true }),
      'bottom-right',
    );

    map.on('load', () => {
      this.ready.set(true);
    });

    map.on('click', (event) => this.handleMapClick(event));
    map.on('mousemove', (event) => this.handleMapHover(event));
    map.on('mouseout', () => {
      map.getCanvas().style.cursor = '';
    });

    this.resizeObserver = new ResizeObserver(() => this.map?.resize());
    this.resizeObserver.observe(container);
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    if (this.noticeTimer) {
      window.clearTimeout(this.noticeTimer);
    }
    this.popup?.remove();
    this.map?.remove();
  }

  async zoomToLayer(layer: LayerDefinition): Promise<void> {
    try {
      const extent = await firstValueFrom(this.catalog.getExtent(layer.id));
      const map = this.map;
      if (!map) {
        return;
      }

      const bounds: [[number, number], [number, number]] = [
        [extent.minX, extent.minY],
        [extent.maxX, extent.maxY],
      ];
      const camera = map.cameraForBounds(bounds, {
        padding: 80,
        maxZoom: 16,
      });
      const fittedZoom = Math.min(camera?.zoom ?? map.getZoom(), 16);
      const zoom = Math.max(fittedZoom, layer.minZoom);

      map.easeTo({
        center: camera?.center ?? {
          lng: (extent.minX + extent.maxX) / 2,
          lat: (extent.minY + extent.maxY) / 2,
        },
        zoom: Math.min(zoom, map.getMaxZoom()),
        duration: 850,
      });
    } catch {
      this.showNotice('Could not determine the extent for this layer.');
    }
  }

  private baseStyle(): StyleSpecification | string {
    if (environment.mapStyleUrl) {
      return environment.mapStyleUrl;
    }

    return {
      version: 8,
      sources: {
        basemap: {
          type: 'raster',
          tiles: [environment.basemapTilesUrl],
          tileSize: 256,
          maxzoom: 19,
          attribution: environment.basemapAttribution,
        },
      },
      layers: [
        {
          id: 'basemap',
          type: 'raster',
          source: 'basemap',
        },
      ],
    };
  }

  private rebuildLayers(
    layers: readonly LayerDefinition[],
    visibility: Record<string, boolean>,
    opacity: Record<string, number>,
  ): void {
    this.clearManagedLayers();

    // Draw polygons first, then lines, then points so small features are not
    // hidden underneath large fills.
    const ordered = [...layers].sort(
      (a, b) => this.renderPriority(a) - this.renderPriority(b),
    );

    for (const layer of ordered) {
      if (!this.map) {
        return;
      }

      this.map.addSource(layer.id, {
        type: 'vector',
        tiles: [
          `${environment.apiBaseUrl}/tiles/${encodeURIComponent(layer.id)}/{z}/{x}/{y}.pbf`,
        ],
        minzoom: Math.min(layer.minZoom, 22),
        maxzoom: Math.min(Math.max(layer.maxZoom, layer.minZoom), 22),
      });

      const renderIds = this.addRenderLayers(
        layer,
        visibility[layer.id] !== false,
        opacity[layer.id] ?? 1,
      );

      const entry: ManagedLayer = { definition: layer, renderIds };
      this.managed.set(layer.id, entry);
      for (const renderId of renderIds) {
        this.renderToLayer.set(renderId, layer);
      }
    }
  }

  private renderPriority(layer: LayerDefinition): number {
    switch (layer.geometryType) {
      case 'Polygon':
        return 0;
      case 'Unknown':
        return 1;
      case 'LineString':
        return 2;
      case 'Point':
        return 3;
      default:
        return 4;
    }
  }

  private addRenderLayers(
    layer: LayerDefinition,
    visible: boolean,
    userOpacity: number,
  ): string[] {
    if (!this.map) {
      return [];
    }

    const renderIds: string[] = [];
    const layout = { visibility: visible ? 'visible' : 'none' } as const;
    const paintOpacity = this.clampOpacity(userOpacity);

    if (layer.geometryType === 'Polygon' || layer.geometryType === 'Unknown') {
      const fillId = `${layer.id}--fill`;
      this.map.addLayer({
        id: fillId,
        type: 'fill',
        source: layer.id,
        'source-layer': layer.tableName,
        minzoom: layer.minZoom,
        maxzoom: layer.maxZoom,
        layout,
        paint: {
          'fill-color': layer.style.fillColor,
          'fill-opacity': this.clampOpacity(
            layer.style.fillOpacity * paintOpacity,
          ),
        },
      } as unknown as LayerSpecification);
      renderIds.push(fillId);

      const outlineId = `${layer.id}--outline`;
      this.map.addLayer({
        id: outlineId,
        type: 'line',
        source: layer.id,
        'source-layer': layer.tableName,
        minzoom: layer.minZoom,
        maxzoom: layer.maxZoom,
        layout: { ...layout, 'line-join': 'round' },
        paint: {
          'line-color': layer.style.lineColor,
          'line-width': layer.style.lineWidth,
          'line-opacity': this.clampOpacity(
            layer.style.lineOpacity * paintOpacity,
          ),
        },
      } as unknown as LayerSpecification);
      renderIds.push(outlineId);
    }

    if (layer.geometryType === 'LineString' || layer.geometryType === 'Unknown') {
      const lineId = `${layer.id}--line`;
      this.map.addLayer({
        id: lineId,
        type: 'line',
        source: layer.id,
        'source-layer': layer.tableName,
        minzoom: layer.minZoom,
        maxzoom: layer.maxZoom,
        layout: { ...layout, 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': layer.style.lineColor,
          'line-width': layer.style.lineWidth,
          'line-opacity': this.clampOpacity(
            layer.style.lineOpacity * paintOpacity,
          ),
        },
      } as unknown as LayerSpecification);
      renderIds.push(lineId);
    }

    if (layer.geometryType === 'Point' || layer.geometryType === 'Unknown') {
      const circleId = `${layer.id}--circle`;
      this.map.addLayer({
        id: circleId,
        type: 'circle',
        source: layer.id,
        'source-layer': layer.tableName,
        minzoom: layer.minZoom,
        maxzoom: layer.maxZoom,
        layout,
        paint: {
          'circle-color': layer.style.circleColor,
          'circle-radius': layer.style.circleRadius,
          'circle-opacity': this.clampOpacity(
            layer.style.circleOpacity * paintOpacity,
          ),
          'circle-stroke-color': layer.style.circleStrokeColor,
          'circle-stroke-width': layer.style.circleStrokeWidth,
        },
      } as unknown as LayerSpecification);
      renderIds.push(circleId);
    }

    return renderIds;
  }

  private clearManagedLayers(): void {
    if (!this.map) {
      return;
    }

    for (const entry of this.managed.values()) {
      for (const renderId of entry.renderIds) {
        if (this.map.getLayer(renderId)) {
          this.map.removeLayer(renderId);
        }
      }
      if (this.map.getSource(entry.definition.id)) {
        this.map.removeSource(entry.definition.id);
      }
    }

    this.managed.clear();
    this.renderToLayer.clear();
  }

  private applyVisibility(visibility: Record<string, boolean>): void {
    if (!this.map) {
      return;
    }

    for (const entry of this.managed.values()) {
      const value = visibility[entry.definition.id] === false ? 'none' : 'visible';
      for (const renderId of entry.renderIds) {
        if (this.map.getLayer(renderId)) {
          this.map.setLayoutProperty(renderId, 'visibility', value);
        }
      }
    }
  }

  private applyOpacity(opacity: Record<string, number>): void {
    if (!this.map) {
      return;
    }

    for (const entry of this.managed.values()) {
      const factor = this.clampOpacity(opacity[entry.definition.id] ?? 1);
      const style = entry.definition.style;

      for (const renderId of entry.renderIds) {
        if (!this.map.getLayer(renderId)) {
          continue;
        }

        if (renderId.endsWith('--fill')) {
          this.map.setPaintProperty(
            renderId,
            'fill-opacity',
            this.clampOpacity(style.fillOpacity * factor),
          );
        } else if (renderId.endsWith('--outline') || renderId.endsWith('--line')) {
          this.map.setPaintProperty(
            renderId,
            'line-opacity',
            this.clampOpacity(style.lineOpacity * factor),
          );
        } else if (renderId.endsWith('--circle')) {
          this.map.setPaintProperty(
            renderId,
            'circle-opacity',
            this.clampOpacity(style.circleOpacity * factor),
          );
        }
      }
    }
  }

  private handleMapClick(event: MapMouseEvent): void {
    if (!this.map) {
      return;
    }

    const renderIds = this.existingRenderIds();
    if (!renderIds.length) {
      return;
    }

    const features = this.map.queryRenderedFeatures(event.point, {
      layers: renderIds,
    });
    const feature = features[0];
    if (!feature) {
      this.popup?.remove();
      return;
    }

    const layer = this.renderToLayer.get(feature.layer.id);
    if (!layer) {
      return;
    }

    const properties = (feature.properties ?? {}) as Record<string, unknown>;

    this.popup?.remove();
    this.popup = new maplibregl.Popup({
      maxWidth: '360px',
      closeButton: true,
      offset: 12,
    })
      .setLngLat(event.lngLat)
      .setHTML(this.popupHtml(layer, properties))
      .addTo(this.map);
  }

  private handleMapHover(event: MapMouseEvent): void {
    if (!this.map) {
      return;
    }

    const now = performance.now();
    if (now - this.lastHoverCheck < 50) {
      return;
    }
    this.lastHoverCheck = now;

    const renderIds = this.existingRenderIds();
    if (!renderIds.length) {
      this.map.getCanvas().style.cursor = '';
      return;
    }

    const features = this.map.queryRenderedFeatures(event.point, {
      layers: renderIds,
    });
    this.map.getCanvas().style.cursor = features.length ? 'pointer' : '';
  }

  private existingRenderIds(): string[] {
    if (!this.map) {
      return [];
    }
    return [...this.renderToLayer.keys()].filter((id) => this.map?.getLayer(id));
  }

  private popupHtml(
    layer: LayerDefinition,
    properties: Record<string, unknown>,
  ): string {
    const entries = Object.entries(properties).slice(0, 14);
    const rows = entries
      .map(
        ([key, value]) =>
          `<div class="feature-popup__row"><dt>${this.escapeHtml(
            key,
          )}</dt><dd>${this.escapeHtml(this.formatValue(value))}</dd></div>`,
      )
      .join('');

    return `
      <div class="feature-popup">
        <div class="feature-popup__eyebrow">${this.escapeHtml(
          `${layer.schemaName}.${layer.tableName}`,
        )}</div>
        <h3 class="feature-popup__title">${this.escapeHtml(layer.title)}</h3>
        ${
          rows
            ? `<dl class="feature-popup__rows">${rows}</dl>`
            : '<p class="feature-popup__empty">No attributes returned for this feature.</p>'
        }
        <div class="feature-popup__footer">${layer.columnCount} mapped attribute${
          layer.columnCount === 1 ? '' : 's'
        }</div>
      </div>
    `;
  }

  private formatValue(value: unknown): string {
    if (value === null || value === undefined || value === '') {
      return '—';
    }
    if (typeof value === 'boolean') {
      return value ? 'Yes' : 'No';
    }
    if (typeof value === 'object') {
      try {
        const serialised = JSON.stringify(value);
        return serialised.length > 160
          ? `${serialised.slice(0, 157)}…`
          : serialised;
      } catch {
        return String(value);
      }
    }

    const text = String(value);
    return text.length > 160 ? `${text.slice(0, 157)}…` : text;
  }

  private escapeHtml(value: unknown): string {
    return String(value ?? '').replace(/[&<>"']/g, (character) => {
      switch (character) {
        case '&':
          return '&amp;';
        case '<':
          return '&lt;';
        case '>':
          return '&gt;';
        case '"':
          return '&quot;';
        default:
          return '&#39;';
      }
    });
  }

  private clampOpacity(value: number): number {
    if (!Number.isFinite(value)) {
      return 1;
    }
    return Math.max(0, Math.min(1, value));
  }

  private showNotice(message: string): void {
    this.notice.set(message);
    if (this.noticeTimer) {
      window.clearTimeout(this.noticeTimer);
    }
    this.noticeTimer = window.setTimeout(() => this.notice.set(null), 4200);
  }
}
