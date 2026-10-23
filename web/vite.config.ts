import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const workerPath = require.resolve('msw/mockServiceWorker.js');
const csp =
  "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'";
export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    tailwindcss(),
    ...(mode === 'stg02' ? [{
      name: 'stg02-entry',
      configureServer(server: import('vite').ViteDevServer) {
        server.middlewares.use((req, _res, next) => {
          if (req.url?.split('?')[0] === '/stg02') req.url = req.url.replace('/stg02', '/stg02.html');
          next();
        });
      },
    }] : []),
    ...(mode === 'demo'
      ? [
          {
            name: 'demo-worker',
            configureServer(server: import('vite').ViteDevServer) {
              server.middlewares.use('/mockServiceWorker.js', (_req, res) => {
                res.setHeader('Content-Type', 'application/javascript');
                res.end(fs.readFileSync(workerPath));
              });
            },
            closeBundle() {
              fs.copyFileSync(workerPath, 'dist-demo/mockServiceWorker.js');
            },
          },
        ]
      : []),
  ],
  build: {
    outDir: mode === 'stg02' ? 'dist-stg02' : mode === 'demo' ? 'dist-demo' : 'dist',
    ...(mode === 'stg02' ? { rollupOptions: { input: 'stg02.html' } } : {}),
  },
  ...(mode === 'stg02' ? { server: {
    host: '127.0.0.1', port: 4251, strictPort: true,
    proxy: {
      '/v1/read': 'http://127.0.0.1:4252',
      '/o01/v0': 'http://127.0.0.1:4252',
    },
  } } : {}),
  preview: {
    host: '127.0.0.1',
    headers: {
      'Content-Security-Policy': csp,
      'Referrer-Policy': 'no-referrer',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Cross-Origin-Resource-Policy': 'same-origin',
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.{ts,tsx}'],
    setupFiles: ['tests/setup.ts'],
  },
}));
