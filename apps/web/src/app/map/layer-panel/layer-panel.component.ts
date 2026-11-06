import {
  Component,
  HostBinding,
  computed,
  input,
  output,
  signal,
} from '@angular/core';

import {
  CatalogStatus,
  ColorValue,
  LayerDefinition,
} from '../../core/models/layer.model';

@Component({
  selector: 'app-layer-panel',
  templateUrl: './layer-panel.component.html',
  styleUrl: './layer-panel.component.scss',
})
export class LayerPanelComponent {
  readonly open = input(true);
  readonly layers = input.required<readonly LayerDefinition[]>();
  readonly visibility = input.required<Record<string, boolean>>();
  readonly opacity = input.required<Record<string, number>>();
  readonly status = input.required<CatalogStatus>();
  readonly error = input<string | null>(null);

  readonly toggleLayer = output<{ id: string; visible: boolean }>();
  readonly opacityChange = output<{ id: string; value: number }>();
  readonly zoomTo = output<LayerDefinition>();
  readonly showAll = output<void>();
  readonly hideAll = output<void>();
  readonly retry = output<void>();
  readonly close = output<void>();

  readonly query = signal('');
  readonly expanded = signal<string | null>(null);

  readonly filteredLayers = computed(() => {
    const query = this.query().trim().toLowerCase();
    if (!query) {
      return this.layers();
    }

    return this.layers().filter((layer) =>
      `${layer.title} ${layer.id} ${layer.geometryType}`
        .toLowerCase()
        .includes(query),
    );
  });

  readonly activeCount = computed(
    () =>
      this.layers().filter((layer) => this.visibility()[layer.id] !== false)
        .length,
  );

  @HostBinding('class.is-open') get isOpen(): boolean {
    return this.open();
  }

  @HostBinding('class.is-closed') get isClosed(): boolean {
    return !this.open();
  }

  isVisible(layer: LayerDefinition): boolean {
    return this.visibility()[layer.id] !== false;
  }

  opacityPercent(layer: LayerDefinition): number {
    return Math.round((this.opacity()[layer.id] ?? 1) * 100);
  }

  swatch(layer: LayerDefinition): string {
    const value = this.swatchValue(layer);
    return typeof value === 'string' ? value : '#64748b';
  }

  geometryLabel(layer: LayerDefinition): string {
    switch (layer.geometryType) {
      case 'Point':
        return 'Point';
      case 'LineString':
        return 'Line';
      case 'Polygon':
        return 'Polygon';
      default:
        return 'Mixed';
    }
  }

  emitToggle(layer: LayerDefinition): void {
    this.toggleLayer.emit({ id: layer.id, visible: !this.isVisible(layer) });
  }

  emitOpacity(layer: LayerDefinition, event: Event): void {
    const input = event.target as HTMLInputElement;
    this.opacityChange.emit({ id: layer.id, value: Number(input.value) / 100 });
  }

  onSearch(event: Event): void {
    this.query.set((event.target as HTMLInputElement).value);
  }

  toggleExpanded(layerId: string): void {
    this.expanded.update((current) => (current === layerId ? null : layerId));
  }

  private swatchValue(layer: LayerDefinition): ColorValue {
    if (layer.geometryType === 'Point') {
      return layer.style.circleColor;
    }
    if (layer.geometryType === 'LineString') {
      return layer.style.lineColor;
    }
    return layer.style.fillColor;
  }
}
