/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ENTRY_MODE?: 'provider' | 'wit';
  readonly VITE_HUB_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
