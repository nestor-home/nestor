/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `off` runs `pnpm dev` without the mock API. */
  readonly VITE_MOCKS?: string;
}
