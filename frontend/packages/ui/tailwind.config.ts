import type { Config } from "tailwindcss";

/**
 * Shared Tailwind preset. Consuming apps do:
 *   import uiPreset from "@fusion-flow/ui/tailwind.preset";
 *   export default { presets: [uiPreset], content: [...] };
 *
 * Maps CSS variables defined in src/theme.css onto Tailwind theme colors.
 */
const preset: Partial<Config> = {
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
          soft: "var(--accent-soft)",
        },
        success: {
          DEFAULT: "var(--success)",
          foreground: "var(--success-foreground)",
          soft: "var(--success-soft)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        sidebar: {
          DEFAULT: "var(--sidebar)",
          border: "var(--sidebar-border)",
          foreground: "var(--sidebar-foreground)",
          active: "var(--sidebar-active)",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      boxShadow: {
        // Tinted toward the foreground color rather than neutral black,
        // matching the reference site's colored-shadow style.
        card: "0 1px 2px 0 rgb(38 62 55 / 0.05), 0 1px 3px 0 rgb(38 62 55 / 0.08)",
      },
    },
  },
  plugins: [],
};

export default preset;
