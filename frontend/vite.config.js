import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// Pocket EP PWA. The service worker precaches the app shell only (hashed bundle,
// CSS, index.html, icons). `runtimeCaching` is deliberately empty: the backend
// lives on another origin and live health data must never be served from a
// cache. Registration (and the reload on update) is in src/pwa.js.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: false,
      manifest: {
        id: '/',
        name: 'Pocket EP',
        short_name: 'Pocket EP',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        theme_color: '#13294B',
        background_color: '#13294B',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: '/maskable-192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: '/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          { src: '/monochrome-512.png', sizes: '512x512', type: 'image/png', purpose: 'monochrome' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png}'],
        globIgnores: ['pocket-ep-*.svg'],
        navigateFallback: 'index.html',
        runtimeCaching: [],
        cleanupOutdatedCaches: true,
        skipWaiting: true,
        clientsClaim: true,
      },
    }),
  ],
})
