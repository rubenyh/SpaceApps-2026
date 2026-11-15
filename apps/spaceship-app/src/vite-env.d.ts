/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the onboard API. Default: http://127.0.0.1:8000 */
  readonly VITE_ONBOARD_API_URL?: string;
  /** Demo wellbeing PINs as JSON, e.g. {"ast-01":"1111"}. Default: lib/wellbeingPins.ts */
  readonly VITE_WELLBEING_PINS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
