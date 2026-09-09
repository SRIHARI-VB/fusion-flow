import type { Config } from "tailwindcss";
// Relative import (not the package's "exports" subpath) — Tailwind loads this config file
// itself via its own jiti-based TS loader outside of Vite's resolver, so we avoid relying on
// package.json "exports" subpath resolution here for robustness.
import uiPreset from "../packages/ui/tailwind.config";

export default {
  presets: [uiPreset],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "../packages/ui/src/**/*.{ts,tsx}",
  ],
} satisfies Config;
