import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/** Match ui/src/config.js: VITE_API_PORT (default 8000; basic_suite uses the same). */
const apiPort = process.env.VITE_API_PORT || '8000';

/** Dev: browser -> same origin (5173) -> proxy -> API (fixes login + WebSocket quirks). */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api-backend': {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api-backend/, ''),
        ws: true,
      },
    },
  },
});
