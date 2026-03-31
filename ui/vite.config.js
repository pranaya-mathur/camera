import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/** Dev: browser -> same origin (5173) -> proxy -> API :8000 (fixes login form + WebSocket quirks). */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api-backend': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api-backend/, ''),
        ws: true,
      },
    },
  },
});
