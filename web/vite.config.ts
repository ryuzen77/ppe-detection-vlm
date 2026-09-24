/// <reference types="vitest/config" />
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

// Backend FastAPI saat pengembangan (npm run dev). Di produksi UI disajikan
// oleh backend itu sendiri, jadi tidak ada proxy.
const BACKEND = process.env.SAFEGUARD_BACKEND ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [svelte()],
  // UI baru disajikan di akar "/"; UI lama tetap di "/legacy/" (cadangan, T33).
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': BACKEND,
      '/ws': { target: BACKEND.replace(/^http/, 'ws'), ws: true },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
