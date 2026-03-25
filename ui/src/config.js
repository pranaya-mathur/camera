const host = import.meta.env.VITE_API_HOST || window.location.hostname;
const port = import.meta.env.VITE_API_PORT || '8000';

export const API_BASE = `http://${host}:${port}`;
export const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${host}:${port}/ws`;
