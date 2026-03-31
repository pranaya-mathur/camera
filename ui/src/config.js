const devProxy = import.meta.env.DEV;

const host =
  import.meta.env.VITE_API_HOST ||
  (typeof window !== 'undefined' ? window.location.hostname : 'localhost');
const port = import.meta.env.VITE_API_PORT || '8000';

/**
 * Dev (`npm run dev`): use Vite proxy prefix so fetches + MJPEG + WS are same-origin.
 * Prod build: hit API directly (set VITE_API_HOST / VITE_API_PORT if UI is not on same host).
 */
export const API_BASE = devProxy ? '/api-backend' : `http://${host}:${port}`;

const wsProto =
  typeof window !== 'undefined' && window.location.protocol === 'https:'
    ? 'wss:'
    : 'ws:';
const wsHostPort =
  devProxy && typeof window !== 'undefined'
    ? window.location.host
    : `${host}:${port}`;
const wsPath = devProxy ? '/api-backend/ws' : '/ws';

export const WS_URL = `${wsProto}//${wsHostPort}${wsPath}`;
