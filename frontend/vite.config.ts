import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Forward API, download, and proof requests to the local nginx/backend
      '/api': { target: 'http://localhost:8081', changeOrigin: true },
      '/d/':  { target: 'http://localhost:8081', changeOrigin: true },
      '/proofs/': { target: 'http://localhost:8081', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // Split vendor and app chunks for better Cloudflare edge-caching
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          query: ['@tanstack/react-query'],
        },
      },
    },
  },
})
