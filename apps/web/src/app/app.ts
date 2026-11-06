import { Component, computed, inject, linkedSignal, signal, viewChild } from '@angular/core';

import { GeoJsonFeature, LayerDefinition } from './core/models/layer.model';
import { LayerCatalogService } from './core/services/layer-catalog.service';
import { LayerPanelComponent } from './map/layer-panel/layer-panel.component';
import { MapViewComponent } from './map/map-view/map-view.component';

@Component({
  selector: 'app-root',
  imports: [LayerPanelComponent, MapViewComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly catalog = inject(LayerCatalogService);
  private readonly mapView = viewChild<MapViewComponent>('mapView');

  readonly layers = this.catalog.layers;
  readonly status = this.catalog.status;
  readonly error = this.catalog.error;

  private readonly narrow = signal(window.matchMedia('(max-width: 900px)').matches);
  readonly panelOpen = signal(!this.narrow());

  readonly visibility = linkedSignal<
    readonly LayerDefinition[],
    Record<string, boolean>
  >({
    source: this.layers,
    computation: (layers, previous) => {
      const next: Record<string, boolean> = {};
      for (const layer of layers) {
        next[layer.id] = previous?.value?.[layer.id] ?? layer.defaultVisible;
      }
      return next;
    },
  });

  readonly opacity = linkedSignal<
    readonly LayerDefinition[],
    Record<string, number>
  >({
    source: this.layers,
    computation: (layers, previous) => {
      const next: Record<string, number> = { ...(previous?.value ?? {}) };
      for (const layer of layers) {
        if (!(layer.id in next)) {
          next[layer.id] = 1;
        }
      }
      return next;
    },
  });

  readonly activeCount = computed(
    () =>
      this.layers().filter((layer) => this.visibility()[layer.id] !== false)
        .length,
  );

  readonly statusTone = computed(() => {
    switch (this.status()) {
      case 'ready':
        return 'ready';
      case 'loading':
      case 'idle':
        return 'loading';
      case 'unconfigured':
        return 'warning';
      default:
        return 'error';
    }
  });

  readonly statusLabel = computed(() => {
    switch (this.status()) {
      case 'ready':
        return 'Live';
      case 'loading':
      case 'idle':
        return 'Connecting';
      case 'unconfigured':
        return 'No database';
      default:
        return 'Offline';
    }
  });

  constructor() {
    this.catalog.load();
  }

  togglePanel(): void {
    this.panelOpen.update((open) => !open);
  }

  setVisibility(layerId: string, visible: boolean): void {
    this.visibility.update((current) => ({ ...current, [layerId]: visible }));
  }

  setOpacity(layerId: string, value: number): void {
    this.opacity.update((current) => ({ ...current, [layerId]: value }));
  }

  showAll(): void {
    this.visibility.set(
      Object.fromEntries(this.layers().map((layer) => [layer.id, true])),
    );
  }

  hideAll(): void {
    this.visibility.set(
      Object.fromEntries(this.layers().map((layer) => [layer.id, false])),
    );
  }

  zoomTo(layer: LayerDefinition): void {
    void this.mapView()?.zoomToLayer(layer);
  }

  flyToFeature(event: { feature: GeoJsonFeature; layer: LayerDefinition }): void {
    this.setVisibility(event.layer.id, true);
    this.mapView()?.flyToFeature(event.feature, event.layer);
  }

  retry(): void {
    this.catalog.load();
  }
}
