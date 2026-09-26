# UI Design Reference

Two dashboard screenshots (light + dark) and one workflow-builder screenshot were used as the visual reference for this build. They are not stored as binary files in this repo; the specs below are the source of truth for implementation.

## Dashboard (light + dark)

- **Sidebar**: fixed left, ~260px. Top: org/workspace switcher (logo icon + org name + team name + chevron). Nav grouped under uppercase small-caps section labels (`MAIN MENU`, `CUSTOMERS`, `MANAGEMENT`, `SETTINGS`). Each nav item: icon + label, active item gets a soft pill background in the accent color with accent-colored icon/text. Bottom of sidebar: user avatar + name + plan badge (e.g. "Pro Plan") + chevron.
- **Topbar**: breadcrumb (e.g. `Dashboard > Overview`, current segment in accent color), centered/right global search input with a `⌘K` kbd hint, notification bell icon, a secondary icon button, user avatar.
- **Page header**: large greeting/title (e.g. "Welcome back, {name}"), right-aligned controls: a period-select dropdown (Daily/Weekly/...), a date-range button with calendar icon, a solid accent-colored primary button with icon (e.g. "Export CSV").
- **KPI stat cards** (grid of 4): uppercase small label, large bold number, small inline mini-bar sparkline top-right, footer row with an info icon on the left and a green "+X% last year" delta on the right.
- **Trend panel** (large, ~2/3 width): title + info icon + overflow menu (`...`), a legend-style total figure, colored dot legend toggles (e.g. "New user" / "Existing user"), a period-toggle button group (Weekly/Monthly/Yearly), a bar chart with hover tooltip card showing a breakdown for the hovered period.
- **Breakdown panel** (~1/3 width): title + subtitle, total figure, a date-range dropdown, a highlighted "Get AI insight" callout row (icon + text + arrow), and a secondary bar chart below.
- **Data table** ("Recent Transactions" or similar): header row with checkbox-select-all, sortable column headers (small up/down caret icons), a search input, a solid accent "+ Add" button, and row-level actions.
- **Color system**: light mode = off-white/white surfaces, charcoal text; dark mode = deep forest-charcoal surfaces (~`#10201A`), same layout and spacing, same accent. Single accent: pine green (~`#165B4C`, `#2A8F6C` in dark mode) used for primary buttons, active nav pill, active toggle states, and the dominant chart series. Positive deltas in green. Implement as CSS variables / Tailwind `dark:` variants driven by shadcn/ui theme tokens — one component tree, token swap only.

## Workflow builder

- **Canvas**: infinite pannable/zoomable canvas (top-left zoom in/out controls) showing rounded white "step" cards ("nodes"), each with a small icon + short title header and a body preview of its configured content (e.g. a message body with an interpolated variable chip, or a list of reply options with per-option port).
- **Connections**: curved bezier edges between small circular ports on the right/left edges of cards, ports colored green when connected.
- **Right-hand palette**: a collapsible panel with a lock/pin icon, organized into labeled category groups (in the reference: `Messages`, `Choices`, `Inputs`, `Payments`, `Ecommerce`), each item a small icon + label tile meant to be dragged onto the canvas.
- **Top bar**: workflow name + back icon on the left, `Static Variables` / `Global Variables` toggles, `Autosave` toggle, undo/redo icons, a solid accent "Save" button with icon on the right.
- **Mapping to our node taxonomy**: reference categories map to our own node groups — `Messages`→messaging actions (send WhatsApp message, etc.), `Choices`→condition/branch nodes, `Inputs`→trigger/data-capture nodes, `Payments`→payment connector actions, `Ecommerce`→order/product actions. Card visual style (icon+title header, body preview, colored ports) is adopted directly for our `@xyflow/react` custom node components.

## Palette tokens (`frontend/packages/ui/src/theme.css` is the live source; this mirrors it)

Forest-green/sage palette:

- Deep Forest / Pine Green: `#0F4C3A` → `#165B4C` — brand accent (`--accent`, `--ring`)
- Soft Sage / Mint Tint: `#EAF4EE` → `#F0F7F3` — muted/secondary surfaces, accent-soft, active sidebar pill
- Clean Off-White: `#FBFBF9` → `#FFFFFF` — page background → card/sidebar surfaces
- Charcoal Slate: `#1A2421` — primary text (`--foreground`)
- Muted Sage Gray: `#5A6E67` → `#70807B` — secondary/muted text, inactive sidebar labels

- `--accent`: `#165B4C` (dark mode: `#2A8F6C`)
- `--accent-foreground`: `#FFFFFF`
- `--success`: `#1F9D55` (dark mode: `#34C286`) — deliberately a different green than the brand accent so deltas stay visually distinct
- `--destructive`: `#DC2626` (dark mode: `#EF4444`) — kept red regardless of theme, not part of the brand palette
- Light surfaces: `#FFFFFF` / `#FBFBF9` (page bg) / `#1A2421` (primary text)
- Dark surfaces: `#10201A` (page bg) / `#17281F` (card bg) / `#EAF4EE` (primary text)

## Typography

- Font: **Outfit** (Google Font), loaded via `<link>` in both apps' `index.html`, set as `fontFamily.sans` in the shared Tailwind preset and as the `body` font-family in `theme.css`. Falls back to the system sans stack if the Google Fonts request fails.
