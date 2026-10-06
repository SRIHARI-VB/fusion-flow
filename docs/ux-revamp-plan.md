# UI/UX Revamp and Automation Simplification Plan

Date: 2026-10-01. Based on a full audit of `frontend/web`, `frontend/packages/ui`, `backend/.../workflows`, `predefined_automations`, the 24 seeded starter templates and 23 components.

Scope: the tenant app (`frontend/web`) and the workflow product end to end. The admin app is touched only where it must follow (recipe catalog, node templates).

---

## 1. Where we are (evidence)

### 1.1 The automation builder is an engine UI, not a product UI

| Fact | Evidence |
|---|---|
| 66 node types; a fully entitled tenant sees ~65 palette tiles plus admin templates | `nodes/__init__.py:212-279`, `NodePalette.tsx` |
| "When a customer says hi, reply with a greeting" needs 4 nodes, 3 edges, 5-6 fields, including typing `trigger.text.body` and choosing `icontains` from a raw enum | `condition_field_compare.py:54`, `NodeInlineForm.tsx:258-262` |
| FAQ auto-responder template: 9 nodes, 8 edges. Guided ordering: 19 nodes, 19 edges | `seed_workflow_starter_templates.py` |
| Every `true`/`false`/option port must be wired exactly once, so "do nothing otherwise" needs a `log.noop` node from the collapsed Advanced group | `validation.py:266-330`, `graph_helpers.py:1-16` |
| Variables are exposed as `{{node_abc123.text.body}}`; the picker appears only after wiring and always appends to the end of the field | `InsertVariableMenu.tsx:21,38`, `NodeInlineForm.tsx:197` |
| Two incompatible syntaxes: `{{...}}` in most fields, bare dotted path in Compare Field, Multi-branch, edge filters, cart path | `template_resolution.py:152-158` |
| Triggers cannot filter. Keyword matching is a false-chained series of Compare nodes | `whatsapp_message_received.py:39-44`, `graph_helpers.build_keyword_condition_chain` |
| Every flow starts with `find_or_create_customer` and `to: {{trigger.from}}` plumbing | all 24 starter graphs |
| Instagram "ask" nodes do not wait. A tap starts a new run, so state is smuggled in payload strings (`module:id`, `SLOT:ctx\|start\|end`) and three "parse" nodes exist to unpack them | `instagram_ask_choice.py:9-41`, `calendar_parse_*`, `module_get_from_choice_payload` |
| 9 nodes plus 2 pollers exist only for one clinic's booking chain (classify_consultation_bucket, ask_period_choice, ask_calendar_slot, parse_slot_choice, parse_mode_choice, is_direct_booking_day, get_all_active_discounts_summary, tickets.get_latest_for_customer, tickets.add_note; feedback and reminder pollers hard-code "Dr. Faheem" and Asia/Kolkata) | `nodes/__init__.py:151-157`, `appointment_reminder_poller.py:188` |
| Four near-duplicate channel families (message_received x4, find_or_create_customer x2, collect_text x2, ask_choice x2) while IG/Telegram/FB have no send node at all | audit section 3 |
| No list indexing in templates, so `records.get_latest`, `tickets.get_latest_for_customer`, `catalog.*summary` exist as workarounds | `templating.py:27-36` |
| Validation runs only on Publish; issues show `[node_id]` with no canvas highlight | `ValidationPanel.tsx:38,64` |
| Test = paste raw JSON; invalid JSON fails silently; no canvas replay | `WorkflowEditorPage.tsx:1007-1036,668` |
| Runs page is unlinked from the UI; "Steps" column shows `loop_guard_count`; traces show `node_id node_type` + raw JSON | `WorkflowRunsPage.tsx:97,131`, `RunStepTrace.tsx:68-92` |
| Starter templates are created unpublishable (all-zero connector UUIDs, `replace_with_your_approved_template_name`) | seed docstring lines 27-40 |
| Autosave checkbox is labelled "UI only, not wired yet"; no dirty indicator; no unsaved guard | `WorkflowEditorPage.tsx:884` |
| A second, simpler layer already exists: `predefined_automations` compiles a wizard config into a graph (10 types, 9 Instagram + 1 WhatsApp). It is a silo: hand-written React wizard per type (230-414 lines each, 20+ routes), no run history, generated workflows also appear in `/workflows` where hand edits get overwritten | `predefined_automations/service.py`, `communication/instagram/*Wizard*.tsx` |

Engine gaps that force the node count up: no failure port (only try/catch container), no reply timeout branch, any inbound message resumes a waiting run, IG postbacks never resume, `WorkflowTrigger.config` is never read at dispatch, multiple workflows fire on the same message with no priority, entitlement checks `record.` but nodes are `records.*`.

### 1.2 The app shell and pages

- Dashboard is 100% mock data and is the default landing route (`Dashboard.tsx:8-43`).
- UI kit has 9 components. No Dialog, Sheet, Select, Tabs, Toast, Tooltip, Popover, Command, Skeleton, Switch, EmptyState, DataTable. Result: 5 modal implementations, 4 switches, 5 tab styles, 3 steppers, 24 inconsistent raw `<select>`s, 41 "Loading…" strings, ~6 empty-state styles.
- ~16 mutation sites have no error handling and there is no global toast. Deletes on Products, Services, Coupons, Offers, Customers and KB have no confirmation.
- No list has pagination, sorting, search or filters (except Inbox search and Visit History filters). Pickers are unsearchable `<select>`s.
- Topbar holds only a breadcrumb and theme toggle. No search, command palette, notifications, business switcher or user menu (footer menu = Sign out).
- Settings is one long scroll (profile, clinic hours, kill switch, team, permissions, sidebar editor, danger zone) behind an owner password gate. Custom fields live elsewhere.
- Inbox: fixed 3-column grid that breaks under 1024px, assignment by raw user ID, single-line composer, no quick-reply insert, 15 s polling.
- Detail pages: none for Customers, Payments, KB, Broadcasts; Order and Ticket detail hang on "Loading..." for 404.
- Tokens: a real but thin shadcn-style variable layer (teal accent `#3C795D`, Inter). Missing warning/info colours, type scale, spacing/z-index/motion tokens, shadow scale.
- No error boundary, no lazy routes, `document.title` is always "Stilltyping" while other copy says "FusionFlow".
- Mobile: 86 responsive prefixes app-wide; Inbox, wizards, wide tables and the clinic board overflow.
- Accessibility: modals do not trap focus or close on Escape, dropdown has no arrow-key nav, calendar cells are clickable divs, `<Link><Button>` nesting.

---

## 2. Design principles (the bar)

1. **One way to do each thing.** One Dialog, one Sheet, one DataTable, one FormField, one empty state, one loading state. Pages compose; they never hand-roll.
2. **Zero jargon for tenants.** No node ids, UUIDs, enum keys, JSON, dotted paths, "connector instance". If a developer concept must exist it lives behind an explicit "Advanced" disclosure that is off by default for Member and Viewer roles.
3. **Progressive disclosure.** Every screen opens in its simplest useful state. Complexity is pulled, never pushed.
4. **Every action answers.** Optimistic update or spinner, then toast with undo for destructive actions, inline error next to the field that caused it.
5. **Preview before commit.** Messages show a phone preview. Automations show a conversation simulation. Templates show the flow before you pick it.
6. **Role-aware by default.** Viewers never see edit controls that will 403. Owners are not re-authenticated to reorder their own sidebar.
7. **Operational screens are mobile-first.** Inbox, Patient Flow, Appointments and the Home page must work on a phone. Builders and settings may be desktop-first.
8. **Shopify-shaped information architecture.** Objects (customers, orders) have list + detail. Settings has a sub-nav. The primary action sits in the page header, secondary actions in an overflow menu.

Apple HIG and Material rules that apply directly: 44px touch targets, 4.5:1 contrast, visible focus rings, 150-300 ms motion with reduced-motion support, labels not placeholders, errors near the field, one primary CTA per screen, confirmation plus undo for destructive actions, tabular numerals for money columns.

---

## 3. Design system and component foundation

### 3.1 Tokens (extend `packages/ui/src/theme.css` and the Tailwind preset)

- Keep the teal accent and Inter. Add `--warning`, `--info`, soft variants for every semantic colour, and a 4-step neutral surface scale (`surface-0..3`) so cards, sheets and popovers have consistent elevation in both themes.
- Type scale tokens: `display 32/40`, `title 24/32`, `heading 18/28`, `body 14/20`, `body-lg 16/24`, `label 12/16 medium uppercase`. Expose as Tailwind utilities (`text-title`) so pages stop writing `text-2xl font-semibold` 26 times.
- Spacing rhythm: 4/8 scale only. Page gutter 24, section gap 32, card padding 20, dense table row 44, comfortable row 52.
- Radius: 12 for cards and sheets, 8 for inputs and buttons, 6 for chips, full for pills.
- Shadow scale: `elevation-1..3`, tinted toward foreground as today.
- Motion tokens: `duration-fast 150`, `duration-base 200`, `duration-slow 300`; `ease-out` enter, `ease-in` exit.
- Z-index scale: `dropdown 20`, `sticky 30`, `sheet 40`, `modal 50`, `toast 60`, `tooltip 70`.
- Number formatting: `Intl.NumberFormat` and `Intl.DateTimeFormat` helpers with the tenant's currency and timezone from business settings. Delete the `$` and `USD` defaults.

### 3.2 Component kit (adopt real shadcn/ui + Radix in `packages/ui`)

Primitives to add: Dialog, AlertDialog, Sheet, Select, Combobox (cmdk), Command, Tabs, Toast (sonner), Tooltip, Popover, DropdownMenu (replace the hand-rolled one), Switch, Checkbox, RadioGroup, Label, Form (RHF + zod bindings), Separator, Breadcrumb, Pagination, Calendar + DatePicker + TimePicker, Alert, Progress, Skeleton, ScrollArea, SegmentedControl, Kbd.

App composites to build once:

| Composite | Replaces |
|---|---|
| `PageHeader` (title, subtitle, back link, primary action, secondary overflow, tabs slot) | 28 ad-hoc headers |
| `DataTable` (TanStack Table: server pagination, sort, column visibility, row selection, bulk bar, sticky header, loading skeleton, empty state, error state) | ~20 hand-written tables |
| `FilterBar` (search, chips, saved views) | Inbox pills, Visit History card |
| `ResourceSheet` (create/edit in a right-side sheet with unsaved guard) | inline form cards that push tables down |
| `EmptyState` (icon, title, body, primary CTA, secondary link) | 6 variants |
| `ConfirmDestructive` (AlertDialog with typed-confirm option and undo toast) | 2 ConfirmDialogs, `window.confirm`, unconfirmed deletes |
| `StatusBadge` with a semantic map (draft, live, paused, failed, pending, paid, overdue) | per-page badge colour choices |
| `StatCard`, `Sparkline` | KpiCard |
| `Stepper` | 3 implementations |
| `ChannelLogo` | generic lucide icons on connect pages |
| `PhonePreview` (WhatsApp and Instagram chrome) | wizard LivePreviewPanel, NodePreview bubble |
| `VariableChip` / `TemplateEditor` (contentEditable with chips) | `{{...}}` text fields |
| `RuleBuilder` (field picker, friendly operators, AND/OR groups) | Compare Field, Multi-branch, edge filter, JSON filter textareas |
| `RecordPicker` (searchable combobox for customers, products, services) | `<select>` of every customer |

Cross-cutting: `ErrorBoundary` per route, `React.lazy` routes, `useDocumentTitle`, global `QueryClient` `onError` to toast, `useUnsavedChanges` prompt, `aria-live` region for inline status.

---

## 4. App shell and information architecture

### 4.1 Navigation (new IA)

```
Home
Inbox                         (badge: awaiting reply)
Customers
Sales
  Orders · Payments · Catalog (Products, Services, Discounts = Coupons + Offers)
Appointments                  (vertical pack: Patient Flow, Visit History when clinic_queue is on)
Support
  Tickets · Knowledge Base
Marketing
  Broadcasts · Quick Replies · Media
Automations                   (one entry: Recipes + Flows + Runs)
Channels & Apps               (was Connectors)
Settings                      (sub-nav page)
```

- The existing per-user sidebar customization (reorder, rename groups, archive) is kept and moved to a sidebar "Customize" affordance, not inside the password-gated Settings page.
- Module gating stays. Add `empty-nav-state`: a gated item the plan does not include shows as locked with a tooltip and a "Request access" action rather than vanishing.

### 4.2 Shell components

- **Business switcher** at the top of the sidebar: current business, plan badge, popover to switch or create. `/select-business` becomes the fallback, not the only path.
- **Topbar**: breadcrumb with links; global search field that opens the **command palette** (⌘K / Ctrl+K) searching customers, orders, tickets, conversations, automations, pages and actions ("Create order", "Turn off automation X"); **Create** button (customer, order, ticket, broadcast, automation); **notifications** (new conversation, automation failed, payment received, access request approved); theme toggle moves into the user menu.
- **User menu**: profile, preferences (theme, sidebar density), switch business, help and docs, keyboard shortcuts sheet, sign out.
- **Page container**: `max-w-7xl` by default; full-bleed for Inbox, Patient Flow and the flow builder. One padding layer, owned by the layout.
- **Shortcuts**: `g i` inbox, `g c` customers, `c` create, `/` focus search, `?` shortcut sheet.
- Mobile: sidebar becomes a drawer, topbar keeps search and Create, Inbox collapses to list → conversation → details stack.

### 4.3 Home (replace the mock dashboard)

- Setup checklist (persisted, dismissible): connect a channel, import or add customers, add catalog, turn on a first automation, invite a teammate. This replaces the orphaned `/onboarding` page.
- Today: conversations awaiting reply, appointments today (clinic), orders today, payments today, open tickets. Numbers link to filtered lists.
- Automation health: triggered / completed / handed off / failed in the last 7 days, with failures linked to runs.
- Recent activity feed (new conversation, order, payment, ticket, automation hand-off).
- Period selector and export work or are removed.

---

## 5. Feature-by-feature revamp

Every object page follows the same pattern: `PageHeader` → `FilterBar` → `DataTable` → `ResourceSheet` for create and edit → detail page for objects with history.

- **Inbox v2**: responsive 3-pane; conversation list with unread, channel, assignee and automation-paused state; composer with multi-line input, `/` to insert a Quick Reply, attachments from Media Library, templates for out-of-window WhatsApp chats, emoji; assignment via teammate picker; right panel with customer card, open orders, tickets, appointments, custom fields, and an "Automation: on / paused until" toggle; keyboard navigation (j/k, r to reply, e to resolve). Keep polling but move to a 5 s interval with ETag, plan SSE later.
- **Customers**: search, segments (new, returning, tagged, opted-in), tags, import CSV, export; detail page with timeline (conversations, orders, payments, appointments, tickets, automation runs), custom fields, notes.
- **Catalog**: Products and Services with images (Media Library), price with currency, availability; Discounts merges Coupons and Offers into one list with a type column; searchable picker for "applies to".
- **Orders**: line-item editor with product search and totals; status pipeline with explicit buttons and toasts, not a bare select; payment link action; detail shows timeline and linked conversation.
- **Payments**: filters, totals, link to order and customer, refund action when the provider supports it.
- **Tickets**: filters by status/priority/assignee, assignment, internal notes vs customer replies, insert KB article, SLA badge; detail handles 404.
- **Knowledge Base**: markdown editor with preview, categories, search, article page.
- **Appointments**: day/week/month views, confirm/reschedule/cancel actions that message the customer, filter by service and doctor, keyboard-accessible calendar.
- **Patient Flow**: buttons on cards in addition to drag, explanation on invalid drop, mobile column tabs, skeletons.
- **Broadcasts**: detail page with delivery stats (sent, delivered, read, failed, replied), edit route, audience builder reusing `RuleBuilder` over customers, schedule in business timezone, template picker from approved templates.
- **Channels & Apps**: brand logos, grouped by Messaging / Payments / Calendar & Mail / Storage; per-card Test with a visible result; setup guide with webhook URL before connecting; detail page with back link, real tabs, health timeline.
- **Settings** sub-nav: General (business, timezone, currency, hours), Team (invite by email, roles, remove, resend, 2FA later), Permissions, Channels defaults, Custom fields (moved here, with drag reorder), Sidebar, Billing & plan, Danger zone. Step-up applies only to Team, Permissions, Billing and Danger zone, not the whole page.
- **Auth**: forgot and reset password, show-password toggle, one brand name, per-route document titles.

---

## 6. Automations: the new model

### 6.1 Three tiers, one engine

```
Tier 1  Recipes          "Turn on" cards with a 3-6 field form. Zero graph concepts.
Tier 2  Flow Builder     Vertical When / Then / Ask / If editor. Auto layout. No wiring.
Tier 3  Advanced Canvas  Today's React Flow editor, Owner/Admin only, same blocks.
```

All three produce the same `WorkflowVersion.graph`; the engine does not change its contract. Tier 1 and Tier 2 store their own authoring document and a **compiler** emits the graph, exactly the pattern `predefined_automations.build_graph` already proves. Opening a Tier 1 or 2 automation in Tier 3 forks it into a free canvas copy (one-way, with a warning), which removes today's "wizard overwrites hand edits" hazard.

### 6.2 Block vocabulary (what users see)

66 node types collapse into 12 user-facing blocks. Old node types stay registered and become compile targets or aliases, so published graphs keep running.

| Block | What it covers | Compiles to today |
|---|---|---|
| **When…** (trigger) | Customer messages (any channel, keyword/phrase filter, first message only, outside business hours), taps a button, comments on a post, mentions / reacts / replies to a story, order placed, payment received, appointment booked or due in N hours, on a schedule, manually | all 16 triggers + trigger-level filters (new) |
| **Send message** | text, image/video/file, buttons, list, location, contact, approved template; phone preview; channel resolved from the conversation | `whatsapp.send_message`, `connector.action` for IG/Telegram/FB |
| **Ask a question** | answer type: free text, choice (static or from a record list), yes/no, date & time slot, cart. Branches per choice are automatic. Built-in "no reply within N hours" and "invalid answer" handling | ask_question, collect_text, ask_choice, confirm, ask_via_template, ask_for_cart, instagram.* asks, composite branching |
| **If / Otherwise** | visual rule builder: field picker (customer, message, answers, records), friendly operators ("contains", "is one of", "is empty"), AND/OR groups. "Otherwise" is optional; an unwired branch simply ends | condition.field_compare, multi_branch, edge filters |
| **Split by…** | one branch per value of a field or per choice | multi_branch |
| **Wait** | for N minutes/hours, or until business hours | flow.delay, schedule.resolve_business_hours |
| **Records** | find latest / list / create / update any object (built-in or custom), with a filter builder; "tag customer"; "create ticket" and "add note" as presets | records.*, module.*, create_ticket, tickets.* |
| **Order & payment** | create order from answers or cart; send payment link; collect payment (asks and branches paid / not paid) | orders.*, payments.send_razorpay_link, payment.captured |
| **Book appointment** | check availability on the connected calendar, offer slots, confirm, create event, save Appointment record, schedule reminder | ask_calendar_slot, parse_slot_choice, is_direct_booking_day, ask_period_choice, calendar connector actions |
| **Hand over to a person** | pause automation for this conversation, assign to a teammate or team, notify | inbox.pause_automation + create_ticket + notify (new) |
| **Notify team** | internal notification, email via Gmail, Sheets row | connector.action presets |
| **Advanced** (collapsed, Owner/Admin) | Call an API, Run a connector action, Transform data, Compose text, Repeat for each, Run in parallel, Try / catch | http.request, connector.action, data.*, flow.loop, flow.parallel, flow.try_catch |

Hidden entirely from tenants: `log.noop`, `manual.test_trigger`, `connectors.is_connected`, the three payload parsers, `classify_consultation_bucket`, `get_from_choice_payload`, `find_or_create_customer` (becomes automatic, see 6.3).

### 6.3 Engine and backend changes that make the blocks possible

Ordered by leverage. Each is independently shippable and backward compatible.

1. **Trigger filters at dispatch.** Read `WorkflowTrigger.config` in the outbox poller: channel instance, keywords + matching mode, first-message-only, business-hours window. Removes the keyword condition chains from every recipe and template. Add a `priority` and `exclusive` flag so "keyword X" does not fire three automations at once; expose conflicts in the builder ("This phrase is also used by Welcome Menu").
2. **Implicit end.** Validation stops requiring every port to be wired. The compiler inserts the terminal node where needed. Kills the `log.noop` requirement.
3. **Run context and friendly variables.** At run start the engine resolves `customer` (find-or-create by channel identity), `conversation`, `message`, `business` (name, hours, timezone) into reserved roots. Blocks reference `{{customer.name}}`, `{{message.text}}`, `{{answers.<step label>}}`. Each step gets a stable, human label used as its variable namespace; the UI shows chips, never braces. The `find_or_create_customer` node and `to: {{trigger.from}}` disappear from authored graphs.
4. **One template syntax.** Braces everywhere. Bare dotted paths are accepted by the compiler and rewritten. Add list indexing, `first`, `count`, `join`, `default` filters so the "get latest" workaround nodes become unnecessary.
5. **Instagram asks that wait.** Make IG postbacks and quick-reply taps check `find_pending_wait` like DMs do, so `Ask a question` suspends on every channel. Retire payload smuggling and the parser nodes.
6. **Reply timeout and invalid-answer branches.** `Suspend` gets `timeout_minutes`; the poller resumes with `{"timed_out": true}`. Ask blocks validate the answer type and re-prompt N times before taking the "couldn't understand" branch.
7. **Channel-agnostic core nodes.** `message.received`, `message.send`, `message.ask`, `customer.identify` with the channel resolved from the conversation or chosen in the block. Old channel-specific types become aliases resolved at compile time.
8. **Failure default.** A failed step without try/catch marks the run failed, posts a plain-language error on the run, notifies the owner, and does not leave the customer hanging (optional "sorry, a person will follow up" message configured per automation).
9. **Recipe registry becomes declarative.** `PredefinedAutomationType` gains a JSON-schema `config_schema` with UI hints (field order, groups, previews). The frontend renders one generic recipe form from it; the ten hand-written wizards and twenty routes collapse into one. Starter templates are re-expressed as recipes or as Tier 2 documents with no placeholder UUIDs (channel and template are chosen in the form).
10. **Book appointment block.** A composite node family that encapsulates availability check, slot offer, confirmation, calendar event, record upsert and reminder scheduling, parameterised by service, duration, direct-booking weekdays and timezone from business settings. The reminder and feedback pollers become generic recipes ("Remind N hours before", "Ask for feedback N hours after") reading tenant settings instead of hard-coded text.
11. **Housekeeping.** Fix the `record.` vs `records.` entitlement prefix; hide recipe-owned workflows from the free canvas list; link the runs page; label columns correctly; prune stale docstrings.

### 6.4 Builder UX (Tier 2)

- **Entry**: "New automation" opens a goal-based gallery (Reply to common questions, Welcome new customers, Take orders, Book appointments, Follow up after purchase, Capture leads from comments, Hand over to a person). Each card shows the flow as a mini diagram, required channels with a one-click connect, and estimated setup time. "Start from blank" sits last.
- **Canvas**: a vertical, auto-laid-out flow. Blocks are cards with a plain-language summary ("Send: Hi {{customer.first name}}, welcome!"). A `+` sits between blocks and at the end of every branch. Branches render as side-by-side columns and merge visually. No ports, no handles, no free dragging; reorder by drag within the column, move a block between branches via the overflow menu.
- **Block picker**: search plus the 12 blocks grouped by verb (Send, Ask, Decide, Wait, Save, Sell, Book, Hand over, Notify, Advanced). Descriptions visible, not tooltips.
- **Inspector**: right-hand sheet with the block's friendly form. Message blocks show a live phone preview. Variables are inserted at the cursor from a chip picker grouped by Customer, Message, Answers, Records, Business. Choice options need only a label; ids are generated and kept stable on rename.
- **Validation while you build**: a warning dot on the block, a plain sentence in the inspector, and a "Fix" button that jumps to the field. Publish is a single **Turn on** switch with a readiness checklist (channel connected, template approved, fields complete).
- **Test**: a chat simulator. Type as the customer; the flow highlights the active block; answers, records created and messages sent are listed on the side; nothing is actually sent. Replaces the JSON payload box.
- **Runs**: per automation, a list of runs with customer, trigger phrase, outcome (completed, handed over, dropped at step, failed), duration. A run opens as a conversation transcript on the left and the flow with the taken path highlighted on the right; errors in plain language with a retry.
- **Analytics**: triggered, completed, hand-off rate, drop-off per block, median time to complete, top unmatched phrases (feed for new keywords).
- **Versioning**: real autosave of the draft, named versions on Turn on, one-click rollback, diff of block summaries.
- **Lifecycle**: Draft / Live / Paused with a single toggle; "Paused" is a real state, not archive plus trigger deletion.

### 6.5 Tier 3 (advanced canvas) changes

Kept for Owners and Admins, reached via "Open in advanced editor". It receives the new block palette, friendly variable chips, inline validation, run-path highlighting and real autosave. Nothing else is invested there; it is the escape hatch, not the product.

---

## 7. The clinic (Faheem) workflow, measured

Pulled on 2026-10-01 through the API as the clinic owner: workflow "Dr. Faheem Clinic · Instagram Assistant" (`f54e719d-24b6-4092-ae8a-e7ec085f8e53`), published version 31.

### 7.1 Size and shape

| Measure | Value |
|---|---|
| Nodes / edges in the published graph | **390 / 561** |
| Versions in 4 days (22 to 26 Sep) | 31, growing from 99 nodes to 390 |
| Node types used | 26 of the 66 |
| `condition.field_compare` nodes | 119 (66 of them route on a postback literal, 49 on a node output such as `resolve-ortho-today.is_closed`) |
| `connector.action` sends | 103 (60 button templates, 33 DMs, 4 quick replies, 3 calendar events, 2 private replies, 1 Meet) |
| Distinct message texts | 60, so 37 send nodes are copies of another message |
| Distinct postback literals the graph routes on | 66 (`DIRECT_ORTHO_TOMORROW_AFTERNOON`, `DUPBOOK_CANCEL_OTHER`, `ASKDOC_NO_EMERGENCY`, `SLOT:`, `MODE:`…) |
| Keyword intents | one `condition.multi_branch` with 120 cases (greetings, thanks, "is this a bot", cost, EMI, emergency words, treatments, duration, pain, call me, medicines, reschedule, cancel, Sunday, FAQ words, status, address, support, today/tomorrow/later) |
| Record writes | 49 upserts: 19 ticket creates, 18 appointment creates, 7 customer name updates, 5 updates |
| Duplication | 143 of 390 nodes are exact copies of 53 patterns once ids and texts are stripped; `is_direct_booking_day` appears 16 times, `resolve_business_hours` 13, `ask_calendar_slot` 12, `collect_text` 15 |
| Runs | 316 in 5 days, **49 failed (15%)** |

The whole ortho / other duplication exists because the concern bucket (Braces vs General) has to be carried from tap to tap inside the payload string. Every screen after the concern choice is built twice: `DAY_ORTHO_*` / `DAY_OTHER_*`, `TIME_*`, `DIRECT_*`, `ASKDOC_*`, `DUPBOOK_*`, each with its own business-hours check, Sunday check, "time already passed" check, slot lookup, ticket, appointment and confirmation.

### 7.2 Conversation it actually implements

1. First-time vs returning greeting (looks up last ticket to say "last time you asked about…"), main menu: Consultation, Treatments, Info, Support.
2. Treatments: 6 category pages (2 button screens of 3), each with a text card and "Book / See other / Back"; a dynamic services list from the Catalog (2 pages of 3, 🎁 for discounts) with a service detail and a classifier that maps the picked service back to ORTHO or OTHER.
3. Consultation: discount summary → concern (Braces / Other / Emergency) → create ticket → "anything to tell the doctor?" (optional note) → duplicate-request check (keep / cancel & rebook) → day (Today / Tomorrow / Later) → Sunday and closed-day handling → direct-booking weekday → period (Morning / Afternoon / Evening, skipping passed periods) → real Google Calendar slots → Online or In-person → Meet link or calendar event → appointment record → confirmation with Check Status button. Non-direct days fall back to "requested" appointments the staff confirm.
4. Emergency: open-now check, call-the-clinic message, emergency slot request with patient name and description.
5. Info (open / closed now with hours and map link), Support (emergency vs normal query → ticket), Check Status (latest ticket), reschedule and cancel intents, ~15 canned FAQ answers (cost, EMI, duration, pain, medicines, Sunday, parking, insurance…), comment auto-reply.

### 7.3 Why it fails in production (sample of 25 failed runs)

- 12 × `send_button_template / send_direct_message requires non-empty 'recipient_id'…`: a variable resolved to empty because the referenced node did not run on that path (unresolved `{{…}}` becomes `''` silently).
- 4 × Meta rejected the send with an HTML error page (rate limit or transient) and the run died; no retry branch, no customer-facing fallback.
- 4 × a `collect_text` wait expired or was resumed by an unrelated message.
- 1 × `create_event requires non-empty 'summary','start','end'` (same empty-variable cause).
- 1 × "The requested user cannot be found" (24-hour window or blocked user).

Every one of these is an engine or block-design problem, not an authoring mistake: no reply timeout branch, any message resumes a wait, no failure default, and empty variables pass validation.

### 7.4 What the same assistant looks like in the new model

Recipe **"Clinic assistant"** (one form) plus two follow-up recipes. Equivalent block count if built in the flow builder: about 25 blocks and 0 manual wires, versus 390 nodes and 561 edges.

| Today | New model |
|---|---|
| 120-case keyword multi-branch + 66 postback compares | **When: customer messages** with an intent table (phrase groups → branch) and **Ask a question** blocks whose button taps resume the same run, so no payload literals exist |
| ORTHO / OTHER duplicated subtrees (≈180 nodes) | one **Ask: What's this about?** with options from a "Concern" list; the answer is a variable, not a fork |
| day → Sunday check → direct-booking check → period → passed-period check → calendar slots → mode → Meet or event → record (≈130 nodes) | one **Book appointment** block configured with service list, fee per service, direct-booking weekdays, hours and periods from Business settings, modes offered, calendar connector |
| duplicate-request check, keep / cancel (12 nodes × 2) | built into Book appointment ("if an open request exists, ask keep or replace") |
| create ticket + add note + "tell the doctor?" (≈30 nodes) | **Ask** (optional note) + **Create ticket** preset with the note attached |
| 6 treatment category pages + 2 service pages + classifier (≈40 nodes) | **Ask: pick a treatment** sourced from Catalog categories, paged automatically, with "Book this" leading into Book appointment carrying the service |
| 3 business-settings lookups + 13 hours resolvers | run context `{{business.*}}` and a **Wait until open / If open now** condition |
| 15 FAQ reply nodes behind keyword cases | one **FAQ** table (phrases → answer) in the recipe form, or 1 Split-by block |
| emergency subtree (≈20 nodes) | intent "Emergency" → **Hand over to a person** with an urgent ticket and the call-us message |
| reminder and feedback pollers hard-coded to this clinic | recipes "Remind N hours before" and "Ask for feedback N hours after" |

Setup time target for a new clinic: under 15 minutes, filling services, fees, hours, direct-booking days, FAQ answers and a phone number.

### 7.5 Cutover plan for the demo tenant

1. Keep version 31 live; nothing in Phases 0-3 changes its behaviour unless the per-workflow "Instagram asks wait for reply" flag is turned on for it (leave it off).
2. Build the "Clinic assistant" recipe against the same business, services and calendar in a draft.
3. Replay the 316 historical runs' first messages through the simulator for both and compare the transcripts; fix gaps in the recipe form rather than adding blocks.
4. Turn the recipe on with `exclusive` priority above the old workflow, keep the old one paused for a week, then archive it.
5. Delete `catalog.classify_consultation_bucket`, the payload parsers and the clinic-specific pollers once no published graph references them.

---

## 8. Delivery plan

Phases are sequential for the frontend but Phase 3 (backend) starts in parallel with Phase 1. Each phase ends in a shippable state.

| Phase | Weeks | Outcome |
|---|---|---|
| **0 Foundation** | 1-2 | Tokens, shadcn/Radix kit, composites (PageHeader, DataTable, ResourceSheet, EmptyState, ConfirmDestructive, FormField), toast + global error handling, error boundaries, lazy routes, document titles, Intl formatters. Confirmation on every delete. Silent failures gone. |
| **1 Shell** | 2-3 | New IA, business switcher, command palette, notifications, user menu, Settings sub-nav with scoped step-up, real Home with setup checklist, sidebar customize affordance. |
| **2 Operations** | 3-4 | Customers (list, detail, import), Catalog with images and Discounts, Orders with line items, Payments, Tickets, KB, Appointments views, Patient Flow mobile, Broadcasts detail and stats, Channels & Apps, Inbox v2. |
| **3 Engine enablers** (parallel) | 3-4 | Items 1-8 and 11 of section 6.3. Compatibility tests: every seeded template and component compiles and publishes unchanged. |
| **4 Automations v2** | 4-5 | Declarative recipe registry and generic recipe form (migrate 10 predefined types and 24 starters), Tier 2 flow document + compiler + builder, chat simulator, runs and analytics, Turn-on lifecycle, advanced canvas gets the new palette and chips. |
| **5 Vertical packs and polish** | 2 | Book appointment block, reminder and feedback recipes, remove Faheem-specific nodes after cutover, mobile pass, accessibility pass (focus, roles, live regions), i18n scaffolding, admin app alignment for recipes and node templates. |

Roughly 15-20 weeks for one full-stack pair plus a designer for Phases 0-1. If only one track can start, start Phase 0 and Phase 3 together: Phase 0 pays off on every screen, and Phase 3 is the long pole for the automation rewrite.

---

## 9. Success criteria

- "When a customer says hi, reply with a greeting": one recipe card, or 2 blocks with 0 manual connections and 2 fields.
- FAQ auto-responder: 1 recipe form (topics + answers), or ≤ 4 blocks.
- Appointment booking: 1 recipe form, or ≤ 6 blocks; no parser or classifier nodes anywhere in the catalog.
- Default block picker ≤ 12 entries. Advanced hidden for Member and Viewer.
- Zero raw ids, enum keys, JSON or dotted paths visible to a tenant outside Advanced.
- Validation visible while editing; Turn on succeeds on first try for every gallery recipe when prerequisites are met.
- Every mutation shows success or a recoverable error. Every destructive action is confirmed and most are undoable.
- All lists paginate, search and sort through one DataTable.
- Inbox, Home, Appointments and Patient Flow pass a 375 px manual test.
- Lighthouse accessibility ≥ 95 on Home, Inbox, Customers and the builder.
- Time from signup to first live automation under 5 minutes in a usability test with a non-technical owner.

---

## 10. Decisions needed

1. **Brand**: one product name (copy currently mixes "Stilltyping" and "FusionFlow"). Keep the teal palette or refresh with the rename.
2. **Advanced canvas**: keep as Tier 3 for Owners/Admins (recommended, lowest risk) or retire after Tier 2 reaches parity.
3. **Instagram asks that wait** (6.3 item 5) changes the live clinic flow's behaviour on tap. Recommended to ship behind a per-workflow flag and move the clinic to the new recipe explicitly.
4. **Sequencing**: shell-first (visible quickly) versus automations-first (the differentiator). Recommended: Phase 0 + Phase 3 together, then 1, 2, 4, 5.
5. **Demo safety**: whether to apply the two cheapest engine fixes (empty-variable validation and a send retry with a customer-facing fallback) to the live clinic workflow before the recipe exists, since 15% of its runs currently fail.
