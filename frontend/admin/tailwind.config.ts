import type { Config } from "tailwindcss";
import uiPreset from "../packages/ui/tailwind.config";

export default {
  presets: [uiPreset],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "../packages/ui/src/**/*.{ts,tsx}",
  ],
} satisfies Config;
