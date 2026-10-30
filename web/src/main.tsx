import "@fontsource-variable/fraunces/full.css";
import "@fontsource-variable/instrument-sans/index.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles/app.css";

import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { NoticeProvider } from "@/components/notices";
import { TooltipProvider } from "@/components/ui/tooltip";
import { I18nProvider } from "@/i18n";
import { ThemeProvider } from "@/lib/theme";
import { createAppRouter, createQueryClient } from "./router";

async function start() {
  // `pnpm dev` runs on the mock API unless NESTOR_API points the proxy at a real Nestor
  if (import.meta.env.DEV && import.meta.env.VITE_MOCKS !== "off") {
    const { startMocks } = await import("./mocks/browser");
    await startMocks();
  }
  const queryClient = createQueryClient();
  const router = createAppRouter({ queryClient });
  const root = document.getElementById("root");
  if (!root) throw new Error("#root missing from index.html");
  createRoot(root).render(
    <StrictMode>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <I18nProvider>
            <TooltipProvider delay={400}>
              <NoticeProvider>
                <RouterProvider router={router} />
              </NoticeProvider>
            </TooltipProvider>
          </I18nProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </StrictMode>,
  );
}

void start();
