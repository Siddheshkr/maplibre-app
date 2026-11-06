import {
  Component,
  HostBinding,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import {
  CatalogStatus,
  ColorValue,
  GeoJsonFeature,
  LayerDefinition,
} from '../../core/models/layer.model';
import { LayerCatalogService } from '../../core/services/layer-catalog.service';

interface LayerFeaturesState {
  loading: boolean;
  features: GeoJsonFeature[];
  error: string | null;
  loaded: boolean;
}

@Component({
  selector: 'app-layer-panel',
  templateUrl: './layer-panel.component.html',
  styleUrl: './layer-panel.component.scss',
})
export class LayerPanelComponent {
  private readonly catalog = inject(LayerCatalogService);

  readonly open = input(true);
  readonly layers = input.required<readonly LayerDefinition[]>();
  readonly visibility = input.required<Record<string, boolean>>();
  readonly opacity = input.required<Record<string, number>>();
  readonly status = input.required<CatalogStatus>();
  readonly error = input<string | null>(null);

  readonly toggleLayer = output<{ id: string; visible: boolean }>();
  readonly opacityChange = output<{ id: string; value: number }>();
  readonly zoomTo = output<LayerDefinition>();
  readonly selectFeature = output<{ feature: GeoJsonFeature; layer: LayerDefinition }>();
  readonly showAll = output<void>();
  readonly hideAll = output<void>();
  readonly retry = output<void>();
  readonly close = output<void>();

  readonly query = signal('');
  readonly expanded = signal<string | null>(null);
  readonly featuresState = signal<Record<string, LayerFeaturesState>>({});
  readonly featureFilterQuery = signal<Record<string, string>>({});
  readonly selectedFeatureId = signal<string | number | null>(null);

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
    const isExpanding = this.expanded() !== layerId;
    this.expanded.update((current) => (current === layerId ? null : layerId));
    if (isExpanding) {
      const layer = this.layers().find((l) => l.id === layerId);
      if (layer && !this.featuresState()[layerId]?.loaded) {
        this.loadFeatures(layer);
      }
    }
  }

  onZoomTo(layer: LayerDefinition): void {
    if (!this.isVisible(layer)) {
      this.toggleLayer.emit({ id: layer.id, visible: true });
    }
    this.zoomTo.emit(layer);
    this.loadFeatures(layer);
  }

  loadFeatures(layer: LayerDefinition): void {
    this.featuresState.update((current) => ({
      ...current,
      [layer.id]: {
        loading: true,
        features: current[layer.id]?.features ?? [],
        error: null,
        loaded: false,
      },
    }));

    this.catalog.getFeatures(layer.id, 500).subscribe({
      next: (res) => {
        this.featuresState.update((current) => ({
          ...current,
          [layer.id]: {
            loading: false,
            features: res.features ?? [],
            error: null,
            loaded: true,
          },
        }));
      },
      error: (err) => {
        const errorMsg =
          err?.error?.detail || err?.message || 'Could not load features for this layer.';
        this.featuresState.update((current) => ({
          ...current,
          [layer.id]: {
            loading: false,
            features: [],
            error: errorMsg,
            loaded: true,
          },
        }));
      },
    });
  }

  onFeatureClick(feature: GeoJsonFeature, layer: LayerDefinition): void {
    const featId = this.getFeatureIdentifier(feature);
    this.selectedFeatureId.set(featId);

    if (!this.isVisible(layer)) {
      this.toggleLayer.emit({ id: layer.id, visible: true });
    }

    this.selectFeature.emit({ feature, layer });
  }

  getFeatureIdentifier(feat: GeoJsonFeature, fallbackIndex?: number): string | number {
    if (feat.id !== undefined && feat.id !== null) {
      return feat.id;
    }
    const props = feat.properties;
    if (props && props['fid'] !== undefined && props['fid'] !== null) {
      return String(props['fid']);
    }
    if (props && props['id'] !== undefined && props['id'] !== null) {
      return String(props['id']);
    }
    return fallbackIndex !== undefined ? fallbackIndex : 'feature';
  }

  onFeatureSearch(layerId: string, event: Event): void {
    const val = (event.target as HTMLInputElement).value;
    this.featureFilterQuery.update((current) => ({ ...current, [layerId]: val }));
  }

  getFilteredFeatures(layerId: string): GeoJsonFeature[] {
    const all = this.featuresState()[layerId]?.features ?? [];
    const q = (this.featureFilterQuery()[layerId] ?? '').trim().toLowerCase();
    if (!q) {
      return all;
    }
    return all.filter((feat) => {
      const title = this.getFeatureTitle(feat).toLowerCase();
      const sub = this.getFeatureSubtitle(feat).toLowerCase();
      return title.includes(q) || sub.includes(q);
    });
  }

  getFeatureTitle(feature: GeoJsonFeature, fallbackIndex?: number): string {
    const props = feature.properties ?? {};
    const priorityKeys = [
      'ia_name',
      'name',
      'title',
      'label',
      'parcel_no',
      'plot_no',
      'facility_name',
      'road_name',
      'category',
      'feature_id',
      'id',
      'fid',
    ];

    for (const key of priorityKeys) {
      const val = props[key];
      if (val !== undefined && val !== null && String(val).trim()) {
        return String(val).trim();
      }
    }

    // Check any string property with 'name' or 'title' in key
    for (const [k, v] of Object.entries(props)) {
      if (/name|title|label|desc/i.test(k) && v && typeof v === 'string') {
        return v.trim();
      }
    }

    // Fallback to first non-empty primitive value
    for (const [k, v] of Object.entries(props)) {
      if (typeof v === 'string' || typeof v === 'number') {
        return `${k}: ${v}`;
      }
    }

    return fallbackIndex !== undefined ? `Feature #${fallbackIndex + 1}` : 'Feature';
  }

  getFeatureSubtitle(feature: GeoJsonFeature): string {
    const props = feature.properties ?? {};
    const subParts: string[] = [];

    const interestingKeys = [
      'district',
      'state',
      'category',
      'area_acre',
      'area_sqm',
      'status',
      'road_class',
      'type',
    ];

    for (const key of interestingKeys) {
      const val = props[key];
      if (val !== undefined && val !== null && String(val).trim()) {
        if (key.includes('area')) {
          const num = Number(val);
          subParts.push(`${key.replace('_', ' ')}: ${isNaN(num) ? val : num.toFixed(2)}`);
        } else {
          subParts.push(String(val));
        }
      }
      if (subParts.length >= 2) break;
    }

    return subParts.join(' · ');
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
