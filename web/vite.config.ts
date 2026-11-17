import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { msw } from "msw/vite";
import { defineConfig } from "vitest/config";

// The admin is served by Nestor itself: the build lands in the Python package's static folder.
const outDir = fileURLToPath(new URL("../src/nestor/admin/static/app", import.meta.url));

// test files that replace a module with `vi.mock`: run apart, in their own module graph
const MOCKING = ["src/features/screens.a11y.test.tsx", "src/features/people/voice.test.tsx"];

export default defineConfig({
  plugins: [
    // routes load on demand in the browser; under test they are part of the module graph from the
    // start, so no test pays for transforming a lazy route chunk inside its own time budget
    tanstackRouter({ target: "react", autoCodeSplitting: !process.env.VITEST, routesDirectory: "src/routes" }),
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
    // the mock API renders its messages with Nestor's own catalogues, next door in the repository
    fs: { allow: [".", fileURLToPath(new URL("../src/nestor/locales", import.meta.url))] },
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
          // the restart flow asks whether the instance answers again
          "/health": { target: process.env.NESTOR_API, changeOrigin: true },
        }
      : {},
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    testTimeout: 15_000, // whole-app tests render the shell and its queries; a busy machine is slow
    // Files share one module graph instead of reloading the app each (`isolate: false`): `setup.ts` puts back after
    // every test what one may change (see AGENTS.md, "Front tests"), and files run in random order so that a leak
    // shows up. The files that replace a module (`vi.mock`) keep their own graph: a replaced module would leak.
    sequence: { shuffle: { files: true, tests: false } },
    projects: [
      {
        extends: true,
        test: {
          name: "shared",
          isolate: false,
          include: ["src/**/*.test.{ts,tsx}"],
          exclude: ["e2e/**", "node_modules/**", ...MOCKING],
        },
      },
      { extends: true, test: { name: "isolated", include: MOCKING } },
    ],
  },
});
