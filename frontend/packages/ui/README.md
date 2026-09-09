# @fusion-flow/ui

Shared Tailwind CSS + hand-written component primitives (Button, Card, Badge, Input, Table,
Avatar, DropdownMenu), theme tokens (light/dark CSS variables from `docs/design/README.md`),
`ThemeProvider`/`useTheme`, and `ThemeToggle`.

## Consumption model: source, not a build step

This package is consumed **directly from TypeScript source** via npm workspaces (no pnpm in
this sandbox — see `frontend/web/README.md`), not via a pre-built `dist/`. `package.json`
`main`/`types` point straight at `src/index.ts`. Both `frontend/web` and `frontend/admin` are
Vite apps, and Vite's esbuild-based transform pipeline happily transpiles `.ts`/`.tsx` files
reached through a workspace symlink in `node_modules/@fusion-flow/ui`, for both `vite dev` and
`vite build` (Rollup uses the same esbuild plugin for transforms during build). This avoids
needing a separate `tsup`/`vite build --mode lib` step (and the associated watch-mode wiring)
for a package that changes constantly during early development.

If this package is ever published outside the monorepo or consumed by a non-Vite/non-esbuild
toolchain, switch `main`/`types`/`exports` to a built `dist/` (e.g. via `tsup src/index.ts
--dts --format esm`) — the source layout underneath does not need to change.

## Tailwind preset

`tailwind.config.ts` exports a preset (`colors`, `borderRadius`, `boxShadow`) that maps the
CSS variables in `src/theme.css` onto Tailwind theme colors (`accent`, `success`, `background`,
`card`, `border`, `muted`, `secondary`, `destructive`, `sidebar`, ...). Consuming apps:

```ts
// tailwind.config.ts in frontend/web or frontend/admin
import uiPreset from "@fusion-flow/ui/tailwind.preset";
export default {
  presets: [uiPreset],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "../packages/ui/src/**/*.{ts,tsx}",
  ],
};
```

Each app must import `src/theme.css` once (e.g. in its root `index.css`) to get the actual
CSS variable values.

## Palette tokens (source of truth: `docs/design/README.md`)

- `--accent: #F97316`, `--accent-foreground: #FFFFFF`, `--success: #16A34A`
- Light: card/bg `#FFFFFF`, page bg `#F8FAFC`, primary text `#0F172A`
- Dark: page bg `#111214`, card bg `#1A1B1E`, primary text `#F1F5F9`

Secondary/muted/border/destructive tokens were added for coherent real components; see
`src/theme.css` for the full list.
