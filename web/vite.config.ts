import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { msw } from "msw/vite";
import { defineConfig } from "vitest/config";

// The admin is served by Nestor itself: the build lands in the Python package's static folder.
const outDir = fileURLToPath(new URL("../src/nestor/admin/static/app", import.meta.url));

export default defineConfig({
  plugins: [
    tanstackRouter({ target: "react", autoCodeSplitting: true, routesDirectory: "src/routes" }),
    react(),
    tailwindcss(),
    // serves the mock service worker in development only; never emitted into the build
    { ...msw({ mode: "worker-only" }), apply: "serve" },
  ],
  // pointing the dev server at a real Nestor turns the mock API off
  define: process.env.NESTOR_API ? { "import.meta.env.VITE_MOCKS": JSON.stringify("off") } : {},
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: { outDir, emptyOutDir: true },
  server: {
    port: 5173,
    // with NESTOR_API set, the dev server talks to a running Nestor instead of the mocks
    proxy: process.env.NESTOR_API
      ? {
          "/api": {
            target: process.env.NESTOR_API,
            changeOrigin: true,
            // sign-in and invitations are checked same-origin: the API must see its own address
            configure: (proxy) => {
              proxy.on("proxyReq", (request) => {
                if (request.getHeader("origin")) request.setHeader("origin", process.env.NESTOR_API ?? "");
                if (request.getHeader("referer")) request.setHeader("referer", `${process.env.NESTOR_API}/`);
              });
            },
          },
          "/connections/callback": { target: process.env.NESTOR_API, changeOrigin: true },
        }
      : {},
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**"],
    css: false,
    testTimeout: 15_000, // whole-app tests render the shell and its queries; a busy machine is slow
  },
});
