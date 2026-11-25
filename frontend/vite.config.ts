import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { VitePWA } from "vite-plugin-pwa";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const apiTarget = env.VITE_DEV_API_TARGET || "http://localhost:8000";

  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        disable: Boolean(process.env.VITEST),
        registerType: "autoUpdate",
        injectRegister: false,
        strategies: "generateSW",
        includeAssets: ["icon.svg", "icon-192.png", "icon-512.png", "offline.html"],
        manifest: {
          name: "OARS Student Solutions",
          short_name: "OARS",
          description:
            "Academic resources, printing and campus services for university students in Uganda.",
          theme_color: "#5B21B6",
          background_color: "#F8FAFC",
          display: "standalone",
          start_url: "/",
          scope: "/",
          lang: "en",
          orientation: "any",
          icons: [
            // SVG maskable icon — works for any size on modern platforms.
            { src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" },
            // PNG icons for platforms that do not support SVG (required for iOS Add to Home Screen).
            { src: "icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
            { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
            { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
          ],
          shortcuts: [
            {
              name: "Find resources",
              url: "/resources",
              description: "Search academic resources",
            },
            {
              name: "Print a document",
              url: "/print",
              description: "Start a new print order",
            },
          ],
        },
        workbox: {
          // ── Precache: app shell only ────────────────────────────────────────
          // Authenticated API responses, private student data, payment info,
          // protected download links, and personal notifications MUST NOT be
          // cached by the service worker. Only versioned static assets and the
          // offline fallback page are precached.
          globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],

          // Serve /index.html for any navigation that is not an API call.
          navigateFallback: "/index.html",
          navigateFallbackDenylist: [
            /^\/api\//,        // Never intercept real API requests.
            /^\/offline\.html$/, // The offline page itself is served directly.
          ],

          // Remove caches from previous service worker versions on activation.
          cleanupOutdatedCaches: true,

          // ── Runtime caching ────────────────────────────────────────────────
          runtimeCaching: [
            // Web fonts: cache-first, long TTL.
            {
              urlPattern: /\.woff2$/,
              handler: "CacheFirst",
              options: {
                cacheName: "fonts-v1",
                expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
              },
            },
            // Public institution list and resource categories are safe to cache
            // briefly (they change rarely and contain no personal data).
            {
              urlPattern: /\/api\/v1\/(institutions|categories)$/,
              handler: "StaleWhileRevalidate",
              options: {
                cacheName: "public-reference-v1",
                expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 4 },
              },
            },
            // Authenticated and personalised API calls: NetworkOnly.
            // This explicit rule documents intent and prevents accidental caching
            // if a future Workbox version changes defaults.
            {
              urlPattern: /\/api\/v1\//,
              handler: "NetworkOnly",
            },
          ],

          // Offline fallback: served when a navigation request fails offline.
        },
      }),
    ],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
        // react-router v7's CJS build require()s an .mjs file, which breaks
        // under Vitest's vmThreads pool. In tests, alias directly to the ESM
        // builds to bypass the exports resolution that picks CJS. Order
        // matters: the /dom subpath must come before the bare specifier.
        ...(process.env.VITEST
          ? {
              "react-router-dom": fileURLToPath(
                new URL("./node_modules/react-router-dom/dist/index.mjs", import.meta.url),
              ),
              "react-router/dom": fileURLToPath(
                new URL("./node_modules/react-router/dist/development/dom-export.mjs", import.meta.url),
              ),
              "react-router": fileURLToPath(
                new URL("./node_modules/react-router/dist/development/index.mjs", import.meta.url),
              ),
            }
          : {}),
      },
    },
    server: {
      host: true,
      port: 5173,
      proxy: { "/api": { target: apiTarget, changeOrigin: true } },
    },
    build: { target: "es2020" },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      css: false,
      pool: "forks",
    },
  };
});
