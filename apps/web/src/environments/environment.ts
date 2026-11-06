export const environment = {
  production: false,
  apiBaseUrl: '/api',
  mapStyleUrl: '',
  basemapTilesUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  basemapAttribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
  initialCenter: [80.0, 22.5] as [number, number],
  initialZoom: 4,
  maxZoom: 22,
};
