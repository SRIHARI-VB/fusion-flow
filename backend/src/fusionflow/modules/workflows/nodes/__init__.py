"""Built-in node types.

The first three (`manual_test_trigger`, `log_noop`, `condition_field_compare`)
are fully generic/self-contained — a small set that doesn't depend on any
other module, so the engine is fully testable in isolation. The next four
(`whatsapp_message_received`, `order_created`, `whatsapp_send_message`,
`create_ticket`) are the connector/fixed-connector-backed node types that
make the plan's M5 sample scenario ("new WhatsApp message → keyword branch
→ create ticket or auto-reply") buildable — they depend on
`modules/connectors/whatsapp` and `modules/tickets` respectively. The next
three (`flow_loop`, `flow_try_catch`, `flow_parallel`) are the container
node types (`can_contain_children = True`) added for the advanced-workflow-
engine phase — genuinely new execution semantics, so unlike most later
node/integration additions (see `run_loop.py`'s and the generic-executor
nodes' docstrings for the "catalog/config, not code" extensibility
principle) these three are real new Python classes, deliberately. The
next four (`connector_action`, `http_request`, `condition_multi_branch`,
`data_transform`) are the generic, highly-parameterized executors that
*are* the extensibility principle in practice — a new connector
capability, a new simple third-party API, a new comparison case, or a new
derived value should reach for one of these (plus, for connector/HTTP
templates, an admin-managed `WorkflowNodeTemplate` catalog row - see
`modules/admin/models.py`) rather than a new node type. The next two
(`whatsapp_interactive_reply_received`, `whatsapp_message_status_updated`)
round out WhatsApp's full message surface (the two new trigger types for
interactive replies and delivery-status updates) — dedicated node types
rather than generic-executor templates *deliberately*, same reasoning as
`whatsapp_send_message` below. `whatsapp_send_message` originally shipped
as 7 separate node types (one per content shape: plain text, media,
location, contact card, template, quick-reply buttons, tap-to-open list)
and was later merged into this one node whose `content` field is a
Pydantic discriminated union across those 7 shapes — same "restructure,
don't migrate" move `whatsapp_ask_choice`'s `source` field pioneered,
since this product had no live tenant data yet when the merge happened.
The final four
(`module_list`, `module_get`, `module_create`, `module_update`) are Phase
6's generic module-CRUD executors — one node type per CRUD verb, dispatching
through a per-module `ModuleQueryAdapter` registry (see
`engine/module_registry.py`) instead of one bespoke node per module x verb,
the same "catalog/config, not code" principle as `connector.action`, applied
to the 9 fixed modules (Products/Services/Coupons/Offers/Customers/Orders/
Payments/Tickets/KB) instead of connectors. Three of those adapters
(`whatsapp.mark_as_read`/business-profile get-update/`find_or_create_customer`)
plus three WhatsApp-specific nodes round out this phase's WhatsApp scope -
those are dedicated node types, not generic-executor templates, per the
same "a channel this central deserves real nodes" reasoning as Phase 5.
`payment_captured` (Phase 8 Part D) is the same thin-echo-trigger shape as
`order_created` - it fires from `RazorpayAdapter.handle_webhook`'s new
`publish_trigger_event` call once a payment is captured; the actual
Razorpay payment-link creation reaches the workflow engine through the
existing generic `connector.action` node, not a new node type.
`record_query`/`record_upsert` (composable-builder redesign, Phase 3) are
friendly front doors over `module.list`/`module.get`/`module.create`/
`module.update` - one node per verb-pair with a `module` picker (see
`module_catalog.py`'s unified fixed-module + custom-object-type catalog)
instead of four separate node types an author has to already know exist;
they dispatch through the exact same `resolve_adapter` lookup, so this is
purely a friendlier config surface, not new business logic.
`whatsapp_ask_choice`/`flow_confirm` (Phase 4) are the "ask and branch"
composable primitives — each registers a static-branch-options function
with `engine/composite_branching.py` so a static-sourced instance
compiles into itself plus an auto-synthesized `condition.multi_branch`
node (see `engine/template_resolution.py::resolve_composite_branches`'s
docstring); a module-sourced `whatsapp.ask_choice` never gets that
treatment and just executes as a plain suspending action.
`whatsapp_collect_text` is a friendly text-only front door over
`whatsapp_ask_question`, delegating to it rather than duplicating its
send+suspend logic. `payments_send_razorpay_link` is a plain,
non-suspending action — deliberately not a "collect payment" node that
also asks COD-vs-online itself (that ask is just an ordinary
`whatsapp.ask_choice`; see that node's module docstring for why one node
can never suspend-to-ask and then branch on its own answer).
`whatsapp_ask_via_template` is the template-send equivalent of
`whatsapp_ask_question`'s pause/resume mechanic — for a workflow with no
guaranteed open 24-hour session (triggered by `order.created`/
`payment.captured`/`manual.test_trigger` rather than an inbound WhatsApp
message) that still needs to capture a reply, not just broadcast; see that
node's module docstring for the full session-window reasoning.
`whatsapp_ask_for_cart` is the genuine-multi-select answer to "can a
customer pick more than one product in one step" — WhatsApp's Commerce
Catalog cart feature, distinct from and not replacing `whatsapp.
ask_choice`'s always-single-select button/list messages.
`orders_create_from_cart` is `orders.create_from_conversation`'s sibling
for that arbitrary-size cart shape, kept as its own node rather than a
second mode on that already-tested node — see both nodes' own module
docstrings.

Importing this package registers all of the above with the process-wide
`node_executor_registry` / `trigger_registry` singletons in
`engine/registry.py` as a side effect — matching `fusionflow.db.models`'s
"import for side effect" pattern for ORM classes.
"""

from fusionflow.modules.workflows.nodes import (  # noqa: F401
    broadcast_scheduled_send,
    condition_field_compare,
    condition_multi_branch,
    connector_action,
    create_ticket,
    data_transform,
    facebook_message_received,
    flow_confirm,
    flow_delay,
    flow_loop,
    flow_parallel,
    flow_try_catch,
    http_request,
    inbox_pause_automation,
    instagram_collect_text,
    instagram_comment_received,
    instagram_find_or_create_customer,
    instagram_mention_received,
    instagram_message_reaction_received,
    instagram_message_received,
    instagram_postback_received,
    instagram_referral_received,
    instagram_story_reply_received,
    log_noop,
    manual_test_trigger,
    module_create,
    module_get,
    module_list,
    module_update,
    order_created,
    orders_create_from_cart,
    orders_create_from_conversation,
    payment_captured,
    payments_send_razorpay_link,
    record_query,
    record_upsert,
    telegram_message_received,
    whatsapp_ask_choice,
    whatsapp_ask_for_cart,
    whatsapp_ask_question,
    whatsapp_ask_via_template,
    whatsapp_collect_text,
    whatsapp_find_or_create_customer,
    whatsapp_get_business_profile,
    whatsapp_interactive_reply_received,
    whatsapp_mark_as_read,
    whatsapp_message_received,
    whatsapp_message_status_updated,
    whatsapp_send_message,
    whatsapp_update_business_profile,
)

__all__ = [
    "broadcast_scheduled_send",
    "condition_field_compare",
    "condition_multi_branch",
    "connector_action",
    "create_ticket",
    "data_transform",
    "facebook_message_received",
    "flow_confirm",
    "flow_delay",
    "flow_loop",
    "flow_parallel",
    "flow_try_catch",
    "http_request",
    "inbox_pause_automation",
    "instagram_collect_text",
    "instagram_comment_received",
    "instagram_find_or_create_customer",
    "instagram_mention_received",
    "instagram_message_reaction_received",
    "instagram_message_received",
    "instagram_postback_received",
    "instagram_referral_received",
    "instagram_story_reply_received",
    "log_noop",
    "manual_test_trigger",
    "module_create",
    "module_get",
    "module_list",
    "module_update",
    "order_created",
    "orders_create_from_cart",
    "orders_create_from_conversation",
    "payment_captured",
    "payments_send_razorpay_link",
    "record_query",
    "record_upsert",
    "telegram_message_received",
    "whatsapp_ask_choice",
    "whatsapp_ask_for_cart",
    "whatsapp_ask_question",
    "whatsapp_ask_via_template",
    "whatsapp_collect_text",
    "whatsapp_find_or_create_customer",
    "whatsapp_get_business_profile",
    "whatsapp_interactive_reply_received",
    "whatsapp_mark_as_read",
    "whatsapp_message_received",
    "whatsapp_message_status_updated",
    "whatsapp_send_message",
    "whatsapp_update_business_profile",
]
