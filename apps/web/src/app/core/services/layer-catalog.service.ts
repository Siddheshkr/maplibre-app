import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  CatalogStatus,
  LayerDefinition,
  LayerExtent,
  LayersResponse,
} from '../models/layer.model';

@Injectable({ providedIn: 'root' })
export class LayerCatalogService {
  private readonly http = inject(HttpClient);

  private readonly layersState = signal<LayerDefinition[]>([]);
  private readonly statusState = signal<CatalogStatus>('idle');
  private readonly errorState = signal<string | null>(null);

  readonly layers = this.layersState.asReadonly();
  readonly status = this.statusState.asReadonly();
  readonly error = this.errorState.asReadonly();
  readonly layerCount = computed(() => this.layersState().length);

  load(): void {
    this.statusState.set('loading');
    this.errorState.set(null);

    this.http
      .get<LayersResponse>(`${environment.apiBaseUrl}/layers`)
      .subscribe({
        next: (response) => {
          this.layersState.set(response.layers ?? []);
          this.statusState.set('ready');
        },
        error: (error: unknown) => {
          const httpError = error as HttpErrorResponse;
          const detail = this.readErrorDetail(httpError);

          this.layersState.set([]);
          this.errorState.set(detail);
          this.statusState.set(
            httpError.status === 503 && /not configured/i.test(detail)
              ? 'unconfigured'
              : 'error',
          );
        },
      });
  }

  getExtent(layerId: string): Observable<LayerExtent> {
    return this.http.get<LayerExtent>(
      `${environment.apiBaseUrl}/layers/${encodeURIComponent(layerId)}/extent`,
    );
  }

  private readErrorDetail(error: HttpErrorResponse): string {
    if (error.status === 0) {
      return 'The spatial API is unreachable. Start services/api on port 8000.';
    }

    const body = error.error as { detail?: unknown } | string | null;
    if (body && typeof body === 'object' && typeof body.detail === 'string') {
      return body.detail;
    }
    if (typeof body === 'string' && body.trim()) {
      return body;
    }
    return error.message || 'The layer catalog could not be loaded.';
  }
}
