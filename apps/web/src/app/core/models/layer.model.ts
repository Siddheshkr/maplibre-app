export type GeometryType = 'Point' | 'LineString' | 'Polygon' | 'Unknown';

/** A colour can be a CSS string or a MapLibre expression (array/object). */
export type ColorValue = string | unknown[] | Record<string, unknown>;

export interface LayerStyle {
  fillColor: ColorValue;
  fillOpacity: number;
  lineColor: ColorValue;
  lineWidth: number;
  lineOpacity: number;
  circleColor: ColorValue;
  circleRadius: number;
  circleStrokeColor: ColorValue;
  circleStrokeWidth: number;
  circleOpacity: number;
}

export interface LayerDefinition {
  id: string;
  schemaName: string;
  tableName: string;
  geometryColumn: string;
  geometryType: GeometryType;
  sourceGeometryType: string;
  srid: number;
  title: string;
  defaultVisible: boolean;
  minZoom: number;
  maxZoom: number;
  featureIdColumn: string | null;
  featureIdType: string | null;
  columnCount: number;
  style: LayerStyle;
}

export interface LayersResponse {
  layers: LayerDefinition[];
  generatedAt: string;
}

export interface LayerExtent {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export type CatalogStatus =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'unconfigured'
  | 'error';

export interface FeatureSelection {
  layer: LayerDefinition;
  properties: Record<string, unknown>;
}
