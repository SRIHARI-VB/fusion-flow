"""Seed the `workflow_starter_templates` catalog (composable-workflow-
builder redesign, Phase 6, plus later follow-up templates) — ready-to-use
example flows, built entirely from the composable node types
(`whatsapp.ask_choice`, `flow.confirm`, `whatsapp.collect_text`,
`whatsapp.ask_for_cart`, `records.query`/`records.upsert`,
`orders.create_from_cart`, `payments.send_razorpay_link`,
`condition.field_compare`, `whatsapp.send_message`/`whatsapp.ask_via_template`),
proving the whole redesign rather than being a fixed, special-cased flow:
every node here is a real, ordinary node type an author can freely delete,
rewire, or add more of after starting from the template (see
`workflows.service.create_workflow_from_starter_template`, the
"instantiate" half of this feature).

Two templates (`order_confirmation_broadcast`, `post_purchase_feedback`)
are triggered by `order.created`, not a WhatsApp message - there's no
guaranteed open 24-hour session, so their first outbound message uses
`whatsapp.send_message` with `content.content_type = "template"` (or
`whatsapp.ask_via_template`) - a pre-approved template - instead of a
plain session-message node. See each graph's own comment below for the
full reasoning.

The `"whatsapp_ordering"` template's `ask_for_cart` node similarly leaves
`catalog_id` as an obviously-fake placeholder string, not a real Meta
Commerce Catalog id - same reasoning, a global template can't know which
catalog a given tenant has connected on Meta's side.

Every graph deliberately leaves every `connector_instance_id`/
`razorpay_connector_instance_id`/`whatsapp_connector_instance_id` config
value as a placeholder all-zero UUID string, NOT a real one — a global,
platform-managed template has no way to know which of a given tenant's
*own* connected WhatsApp/Razorpay instances to reference. This means a
freshly-started workflow from any of these templates is a DRAFT that will
not yet pass `POST /workflows/{id}/publish` (publish-time validation's
rule 2, "disconnected connector reference", correctly flags the
placeholder) until the author opens each WhatsApp/Razorpay node and picks
their own connected instance from the dropdown — exactly the same
one-time setup step already required for any hand-built graph using these
node types today. Every *other* validation rule (reachability, branch
wiring, required fields, loop safety) is satisfied from the moment a
template is instantiated — see `test_workflow_starter_templates.py` for
the regression test asserting exactly that split, for every template here.

Idempotent — matches on `key`, updates in place, safe to re-run after
editing the graphs below.

Usage:
    python scripts/seed_workflow_starter_templates.py
"""

from __future__ import annotations

import asyncio

from fusionflow.db.session import async_session_factory
from fusionflow.modules.admin import service as admin_service

#: Deliberately not a real connector - see module docstring.
_PLACEHOLDER_CONNECTOR_ID = "00000000-0000-0000-0000-000000000000"

#: Deliberately not a real template name - `whatsapp.send_message`'s
#: `TemplateContent.template_name`/`whatsapp.ask_via_template`'s
#: `template_name` both have `min_length=1`, so an
#: empty string would fail Pydantic validation before publish-time
#: validation ever gets a chance to report the friendlier, more actionable
#: "disconnected_connector_reference"-style placeholder story. This value
#: is obviously not a real approved template name, prompting the author to
#: replace it, same spirit as `_PLACEHOLDER_CONNECTOR_ID`.
_PLACEHOLDER_TEMPLATE_NAME = "replace_with_your_approved_template_name"


def _node(
    node_id: str,
    kind: str,
    node_type: str,
    config: dict,
    label: str,
    x: float,
    y: float = 0,
    parent_id: str | None = None,
) -> dict:
    node: dict = {
        "id": node_id,
        "type": kind,
        "data": {"nodeType": node_type, "config": config, "label": label},
        "position": {"x": x, "y": y},
    }
    # Only set for a node embedded inside a `flow.try_catch`/`flow.loop`/
    # `flow.parallel` container (see `order_status_check`'s use of
    # `flow.try_catch` below) - omitted entirely for every other (top-level)
    # node, matching `engine.graph.GraphNode.parent_id`'s own "None for
    # every top-level node" convention.
    if parent_id is not None:
        node["parentId"] = parent_id
    return node


def _edge(edge_id: str, source: str, target: str, source_handle: str | None = None) -> dict:
    edge: dict = {"id": edge_id, "source": source, "target": target}
    if source_handle is not None:
        edge["sourceHandle"] = source_handle
    return edge


# ---------------------------------------------------------------------------
# Template 1: WhatsApp guided ordering (real multi-item cart + optional coupon)
# ---------------------------------------------------------------------------
#
# Multi-item selection is WhatsApp's own Commerce Catalog cart feature
# (`whatsapp.ask_for_cart`), not the interactive list/button messages
# `whatsapp.ask_choice` sends - those are always single-tap, single-select,
# by WhatsApp's own design, regardless of anything this engine could do. A
# customer browses the catalog inside WhatsApp itself, adds any number of
# items, and submits the whole cart as one message; `orders.create_from_cart`
# turns that arbitrary-size cart into a real order with one ordinary loop
# inside its own `execute()`, no unrolled per-item-count branching needed.
# Requires the tenant to have a Meta Commerce Catalog connected to their
# WhatsApp Business Account (external, Meta-side setup) with each product's
# retailer id set to match that product's own id in this system - see
# `whatsapp.ask_for_cart`'s and `WhatsAppAdapter.send_product_list_message`'s
# module docstrings for the full convention.

_PLACEHOLDER_CATALOG_ID = "REPLACE_WITH_YOUR_META_CATALOG_ID"

_ORDERING_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "ask_for_cart",
            "action",
            "whatsapp.ask_for_cart",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "catalog_id": _PLACEHOLDER_CATALOG_ID,
                "body_text": "Hi! Browse our catalog below, add whatever you'd like to your cart, then tap send.",
                "module": "products",
                "filters": {},
                "limit": 30,
                "section_title": "Our Products",
            },
            "Ask customer to build a cart",
            560,
        ),
        _node(
            "ask_coupon",
            "action",
            "flow.confirm",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Do you have a coupon code you'd like to apply?",
            },
            "Ask about a coupon",
            1960,
            0,
        ),
        _node(
            "collect_coupon",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Please enter your coupon code.",
            },
            "Collect the coupon code",
            2240,
            150,
        ),
        _node(
            "lookup_coupon",
            "action",
            "records.query",
            {
                "module": "coupons",
                "operation": "list",
                "filters": {"code_search": "{{collect_coupon.reply}}", "valid_now": True},
                "limit": 1,
            },
            "Look up the coupon",
            2520,
            150,
        ),
        _node(
            "check_coupon",
            "condition",
            "condition.field_compare",
            {"field_path": "lookup_coupon.count", "operator": "gt", "value": 0},
            "Is the coupon valid?",
            2800,
            150,
        ),
        _node(
            "coupon_invalid",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "That coupon code isn't valid or has expired - continuing without a discount."},
            },
            "Send: coupon not valid",
            3080,
            250,
        ),
        _node(
            "confirm_order",
            "action",
            "flow.confirm",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Shall I go ahead and place your order?",
            },
            "Confirm the order",
            3360,
            0,
        ),
        _node(
            "declined_message",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "No problem - message me anytime to start a new order."},
            },
            "Send: order declined",
            3640,
            250,
        ),
        _node(
            "collect_address",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Great! What's the delivery address for this order?",
            },
            "Collect delivery address",
            3640,
            -250,
        ),
        _node(
            "pick_payment",
            "action",
            "whatsapp.ask_choice",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "How would you like to pay?",
                "source": {
                    "kind": "static",
                    "options": [
                        {"id": "cod", "label": "Cash on Delivery"},
                        {"id": "prepaid", "label": "Pay Online"},
                    ],
                },
            },
            "Ask how they'll pay",
            3920,
            -250,
        ),
        # Two node instances, not one shared `payment_method: "{{...}}"` -
        # `orders.create_from_cart`'s `payment_method` is Pydantic-validated
        # (`pattern="^(cod|prepaid)$"`) against the raw config string BEFORE
        # this node's own `execute()` ever interpolates anything, so a
        # templated value would fail that regex check at validation time -
        # a literal "cod"/"prepaid" per branch is the only way this
        # actually works. Unlike the old capped-item design this replaces,
        # each instance's `cart_items_path` handles a cart of ANY size -
        # no per-item-count duplication needed, since the cart itself is a
        # single dynamic list `orders.create_from_cart` loops over in real
        # Python code.
        _node(
            "create_order_cod",
            "action",
            "orders.create_from_cart",
            {
                "customer_id": "{{find_customer.customer.id}}",
                "cart_items_path": "ask_for_cart.reply.product_items",
                "currency": "INR",
                "payment_method": "cod",
            },
            "Create the order (cash on delivery)",
            4200,
            -300,
        ),
        _node(
            "create_order_prepaid",
            "action",
            "orders.create_from_cart",
            {
                "customer_id": "{{find_customer.customer.id}}",
                "cart_items_path": "ask_for_cart.reply.product_items",
                "currency": "INR",
                "payment_method": "prepaid",
            },
            "Create the order (online payment)",
            4200,
            -150,
        ),
        _node(
            "cod_confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": (
                    "Thanks! Your order ({{create_order_cod.item_count}} item(s)) is confirmed, paying cash "
                    "on delivery. We'll deliver to: {{collect_address.reply}}"
                )},
            },
            "Send: cash-on-delivery confirmation",
            4480,
            -300,
        ),
        _node(
            "send_payment_link",
            "action",
            "payments.send_razorpay_link",
            {
                "razorpay_connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "whatsapp_connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "amount": "{{create_order_prepaid.total_amount}}",
                "currency": "INR",
                "order_id": "{{create_order_prepaid.order_id}}",
                "customer_contact": "{{trigger.from}}",
            },
            "Send payment link",
            4480,
            -150,
        ),
        # A second, independent trigger in the same graph: once the real
        # Razorpay webhook confirms payment, tell the customer. `payment.
        # captured`'s `customer_id` is the Payment row's own UUID FK, not a
        # phone number, so a lookup node is needed before we can message
        # them - one more visible, ordinary node, not a hidden step.
        _node("payment_trigger", "trigger", "payment.captured", {}, "Payment received", 4760, 200),
        _node(
            "get_customer_for_payment",
            "action",
            "records.query",
            {"module": "customers", "operation": "get", "item_id": "{{payment_trigger.customer_id}}"},
            "Look up who paid",
            5040,
            200,
        ),
        _node(
            "payment_confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{get_customer_for_payment.item.phone}}",
                "content": {"content_type": "text", "body": "Payment received! Your order is confirmed."},
            },
            "Send: payment confirmation",
            5320,
            200,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "ask_for_cart"),
        _edge("e3", "ask_for_cart", "ask_coupon"),
        _edge("e4e", "ask_coupon", "collect_coupon", source_handle="yes"),
        _edge("e4f", "ask_coupon", "confirm_order", source_handle="no"),
        _edge("e4g", "collect_coupon", "lookup_coupon"),
        _edge("e4h", "lookup_coupon", "check_coupon"),
        _edge("e4i", "check_coupon", "confirm_order", source_handle="true"),
        _edge("e4j", "check_coupon", "coupon_invalid", source_handle="false"),
        _edge("e4k", "coupon_invalid", "confirm_order"),
        _edge("e5", "confirm_order", "collect_address", source_handle="yes"),
        _edge("e6", "confirm_order", "declined_message", source_handle="no"),
        _edge("e7", "collect_address", "pick_payment"),
        _edge("e8", "pick_payment", "create_order_cod", source_handle="cod"),
        _edge("e9", "pick_payment", "create_order_prepaid", source_handle="prepaid"),
        _edge("e10", "create_order_cod", "cod_confirmation"),
        _edge("e11", "create_order_prepaid", "send_payment_link"),
        _edge("e12", "payment_trigger", "get_customer_for_payment"),
        _edge("e13", "get_customer_for_payment", "payment_confirmation"),
    ],
}

# ---------------------------------------------------------------------------
# Template 2: Appointment booking (proves the custom-object-type mechanism)
# ---------------------------------------------------------------------------

_APPOINTMENT_REQUIRED_OBJECT_TYPES = [
    {
        "key": "appointment",
        "name": "Appointment",
        "icon": "calendar",
        "fields": [
            {"key": "service", "label": "Service", "field_type": "text", "required": True, "sort_order": 0},
            {
                "key": "preferred_time",
                "label": "Preferred Date/Time",
                "field_type": "text",
                "required": True,
                "sort_order": 1,
            },
            {
                "key": "status",
                "label": "Status",
                "field_type": "select",
                "options": ["requested", "confirmed", "cancelled"],
                "required": False,
                "sort_order": 2,
            },
        ],
    }
]

_APPOINTMENT_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "pick_service",
            "action",
            "whatsapp.ask_choice",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Hi! What service would you like to book?",
                "source": {
                    "kind": "module",
                    "module": "services",
                    "label_field": "name",
                    "value_field": "id",
                    "limit": 10,
                    "filters": {},
                },
            },
            "Ask which service",
            560,
        ),
        _node(
            "collect_time",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "What date and time works best for you?",
            },
            "Collect preferred time",
            840,
        ),
        _node(
            "create_appointment",
            "action",
            "records.upsert",
            {
                "module": "appointment",
                "operation": "create",
                "fields": {
                    "service": "{{pick_service.reply.label}}",
                    "preferred_time": "{{collect_time.reply}}",
                    "status": "requested",
                    "customer_id": "{{find_customer.customer.id}}",
                },
            },
            "Save the appointment request",
            1120,
        ),
        _node(
            "confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": (
                    "You're booked for {{pick_service.reply.label}} on {{collect_time.reply}}. "
                    "We'll confirm shortly!"
                )},
            },
            "Send booking confirmation",
            1400,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "pick_service"),
        _edge("e3", "pick_service", "collect_time"),
        _edge("e4", "collect_time", "create_appointment"),
        _edge("e5", "create_appointment", "confirmation"),
    ],
}

# ---------------------------------------------------------------------------
# Template 3: WhatsApp support ticket
# ---------------------------------------------------------------------------

_SUPPORT_TICKET_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "pick_category",
            "action",
            "whatsapp.ask_choice",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Hi! What can we help you with today?",
                "source": {
                    "kind": "static",
                    "options": [
                        {"id": "order_issue", "label": "Order Issue"},
                        {"id": "general", "label": "General Question"},
                        {"id": "complaint", "label": "Complaint"},
                    ],
                },
            },
            "Ask which kind of issue",
            560,
        ),
        _node(
            "describe_issue",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Please describe your issue in a few words.",
            },
            "Collect the issue description",
            840,
        ),
        _node(
            "log_ticket",
            "action",
            "create_ticket",
            {
                "subject": "{{pick_category.reply.label}}: {{describe_issue.reply}}",
                "customer_id": "{{find_customer.customer.id}}",
            },
            "Log a support ticket",
            1120,
        ),
        _node(
            "confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": (
                    "Thanks! We've logged your request (ticket {{log_ticket.ticket_id}}) and will get "
                    "back to you soon."
                )},
            },
            "Send ticket confirmation",
            1400,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "pick_category"),
        _edge("e3a", "pick_category", "describe_issue", source_handle="order_issue"),
        _edge("e3b", "pick_category", "describe_issue", source_handle="general"),
        _edge("e3c", "pick_category", "describe_issue", source_handle="complaint"),
        _edge("e4", "describe_issue", "log_ticket"),
        _edge("e5", "log_ticket", "confirmation"),
    ],
}

# ---------------------------------------------------------------------------
# Template 4: Order confirmation broadcast (a non-WhatsApp trigger)
# ---------------------------------------------------------------------------
#
# `order.created` fires for ANY new order - a website checkout, an admin
# action, anything - not just one that started inside an active WhatsApp
# conversation. That means there is no guaranteed open 24-hour session to
# send a plain free-form message through (WhatsApp only allows session
# messages - `whatsapp.send_message` (text/media/buttons/list content),
# `whatsapp.ask_choice`, `whatsapp.collect_text` - within 24 hours of the
# customer's last inbound message; see `nodes/whatsapp_send_message.py`'s
# docstring for this established rule). The first outbound message on a
# non-WhatsApp-triggered path must be a pre-approved template
# (`whatsapp.send_message` with `content.content_type = "template"`)
# instead.

_ORDER_CONFIRMATION_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "order.created", {}, "New order created", 0),
        _node(
            "get_customer",
            "action",
            "records.query",
            {"module": "customers", "operation": "get", "item_id": "{{trigger.customer_id}}"},
            "Look up the customer",
            280,
        ),
        _node(
            "send_confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{get_customer.item.phone}}",
                "content": {
                    "content_type": "template",
                    # Placeholder - the author must create/sync an approved
                    # Utility-category template (WhatsApp Settings) and put its
                    # real name/language here, matching `body_variables`' order
                    # and count to that template's actual {{1}}/{{2}} placeholders.
                    "template_name": _PLACEHOLDER_TEMPLATE_NAME,
                    "language_code": "en_US",
                    "body_variables": ["{{get_customer.item.name}}", "{{trigger.currency}} {{trigger.total_amount}}"],
                },
            },
            "Send order confirmation (template)",
            560,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "get_customer"),
        _edge("e2", "get_customer", "send_confirmation"),
    ],
}

# ---------------------------------------------------------------------------
# Template 5: Post-purchase feedback survey (a second custom-object example)
# ---------------------------------------------------------------------------

_FEEDBACK_REQUIRED_OBJECT_TYPES = [
    {
        "key": "feedback",
        "name": "Feedback",
        "icon": "star",
        "fields": [
            {
                "key": "rating",
                "label": "Rating",
                "field_type": "select",
                "options": ["1", "2", "3", "4", "5"],
                "required": True,
                "sort_order": 0,
            },
            {"key": "comment", "label": "Comment", "field_type": "text", "required": False, "sort_order": 1},
            {"key": "order_id", "label": "Order ID", "field_type": "text", "required": False, "sort_order": 2},
        ],
    }
]

_FEEDBACK_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "order.created", {}, "New order created", 0),
        _node(
            "get_customer",
            "action",
            "records.query",
            {"module": "customers", "operation": "get", "item_id": "{{trigger.customer_id}}"},
            "Look up the customer",
            280,
        ),
        # Same session-window reasoning as Template 4: `order.created` has no
        # guaranteed open WhatsApp session, and a template message has no
        # button/interactive component in this codebase either, so "5
        # tappable rating buttons via a template" was never achievable -
        # `whatsapp.ask_via_template` sends an approved template (whose own
        # approved body text should ask the customer to reply with a number
        # 1-5) and then waits for their free-text reply, same pause/resume
        # mechanic as `whatsapp.ask_question`. Once they reply, the 24-hour
        # session is open again, so `collect_comment`/`thank_you` below can
        # safely stay ordinary session-message nodes.
        _node(
            "ask_rating",
            "action",
            "whatsapp.ask_via_template",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{get_customer.item.phone}}",
                # Placeholder - see Template 4's comment; the approved
                # template's own body text should ask the customer to reply
                # with a number 1-5.
                "template_name": _PLACEHOLDER_TEMPLATE_NAME,
                "language_code": "en_US",
                "body_variables": ["{{get_customer.item.name}}"],
            },
            "Ask for a rating (template)",
            560,
        ),
        _node(
            "collect_comment",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{get_customer.item.phone}}",
                "question": "Thanks! Any comments you'd like to share? (Reply 'none' if not.)",
            },
            "Collect an optional comment",
            840,
        ),
        _node(
            "save_feedback",
            "action",
            "records.upsert",
            {
                "module": "feedback",
                "operation": "create",
                "fields": {
                    "rating": "{{ask_rating.reply}}",
                    "comment": "{{collect_comment.reply}}",
                    "order_id": "{{trigger.order_id}}",
                    "customer_id": "{{get_customer.item.id}}",
                },
            },
            "Save the feedback",
            1120,
        ),
        _node(
            "thank_you",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{get_customer.item.phone}}",
                "content": {"content_type": "text", "body": "Thank you for your feedback - we really appreciate it!"},
            },
            "Send a thank-you message",
            1400,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "get_customer"),
        _edge("e2", "get_customer", "ask_rating"),
        # `whatsapp.ask_via_template` is not a static-source `whatsapp.
        # ask_choice` - it never gets compile-time branch expansion (a
        # template reply is free text, not a fixed option tap), so a single
        # plain edge is correct here, not a fan-out per rating value.
        _edge("e3", "ask_rating", "collect_comment"),
        _edge("e4", "collect_comment", "save_feedback"),
        _edge("e5", "save_feedback", "thank_you"),
    ],
}

# ---------------------------------------------------------------------------
# Template 6: Order status check ("Where's my order?")
# ---------------------------------------------------------------------------

_ORDER_STATUS_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "collect_order_id",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "What's your order id? (You'll find this in your order confirmation message.)",
            },
            "Collect the order id",
            560,
        ),
        # A `flow.try_catch` container: the customer may easily mistype or
        # paste an invalid order id - `records.query`'s "get" operation
        # fails cleanly (Failure) on both a not-found id and a malformed
        # (non-UUID) one, and Try/Catch turns that into a friendly reply
        # instead of the run just failing outright. Both "success" and
        # "error" must be wired here (not just "error") - `flow_try_catch.py`'s
        # own execute() only turns a successful lookup into a followed
        # `Branch(["success"])` when "success" is *itself* wired; leaving it
        # unwired while "error" is wired would silently strand the happy path.
        _node("lookup_order_try", "condition", "flow.try_catch", {}, "Look up the order", 840),
        _node(
            "lookup_order",
            "action",
            "records.query",
            {"module": "orders", "operation": "get", "item_id": "{{collect_order_id.reply}}"},
            "Get the order",
            840,
            100,
            parent_id="lookup_order_try",
        ),
        _node(
            "order_not_found",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "Sorry, I couldn't find an order with that id - please double check and try again."},
            },
            "Send: order not found",
            1120,
            200,
        ),
        _node(
            "send_order_status",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": (
                    "Your order status: {{lookup_order_try.lookup_order.item.status}} - total "
                    "{{lookup_order_try.lookup_order.item.currency}} "
                    "{{lookup_order_try.lookup_order.item.total_amount}}."
                )},
            },
            "Send: order status",
            1120,
            0,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "collect_order_id"),
        _edge("e3", "collect_order_id", "lookup_order_try"),
        _edge("e4", "lookup_order_try", "order_not_found", source_handle="error"),
        _edge("e5", "lookup_order_try", "send_order_status", source_handle="success"),
    ],
}

# ---------------------------------------------------------------------------
# Template 7: Product / stock availability check
# ---------------------------------------------------------------------------

_PRODUCT_AVAILABILITY_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "pick_product",
            "action",
            "whatsapp.ask_choice",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Which product would you like to check?",
                "source": {
                    "kind": "module",
                    "module": "products",
                    "label_field": "name",
                    "value_field": "id",
                    "limit": 10,
                    "filters": {},
                },
            },
            "Ask which product",
            280,
        ),
        _node(
            "get_product",
            "action",
            "records.query",
            {"module": "products", "operation": "get", "item_id": "{{pick_product.reply.id}}"},
            "Look up the product",
            560,
        ),
        _node(
            "check_active",
            "condition",
            "condition.field_compare",
            {"field_path": "get_product.item.is_active", "operator": "eq", "value": True},
            "Is it in stock?",
            840,
        ),
        _node(
            "send_in_stock",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "{{get_product.item.name}} is in stock, priced at {{get_product.item.base_price}}."},
            },
            "Send: in stock",
            1120,
            -100,
        ),
        _node(
            "send_out_of_stock",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "Sorry, {{get_product.item.name}} is currently unavailable."},
            },
            "Send: out of stock",
            1120,
            100,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "pick_product"),
        _edge("e2", "pick_product", "get_product"),
        _edge("e3", "get_product", "check_active"),
        _edge("e4", "check_active", "send_in_stock", source_handle="true"),
        _edge("e5", "check_active", "send_out_of_stock", source_handle="false"),
    ],
}

# ---------------------------------------------------------------------------
# Template 8: Lead capture / Contact Us
# ---------------------------------------------------------------------------

_LEAD_REQUIRED_OBJECT_TYPES = [
    {
        "key": "lead",
        "name": "Lead",
        "icon": "users",
        "fields": [
            {"key": "interest", "label": "Interest", "field_type": "text", "required": True, "sort_order": 0},
            {"key": "message", "label": "Message", "field_type": "text", "required": True, "sort_order": 1},
            {
                "key": "status",
                "label": "Status",
                "field_type": "select",
                "options": ["new", "contacted", "closed"],
                "required": False,
                "sort_order": 2,
            },
        ],
    }
]

_LEAD_CAPTURE_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "pick_interest",
            "action",
            "whatsapp.ask_choice",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Hi! What are you interested in?",
                "source": {
                    "kind": "static",
                    "options": [
                        {"id": "sales", "label": "Sales"},
                        {"id": "support", "label": "Support"},
                        {"id": "partnership", "label": "Partnership"},
                    ],
                },
            },
            "Ask their interest",
            560,
        ),
        _node(
            "describe_need",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Tell us a bit more about what you need.",
            },
            "Collect their message",
            840,
        ),
        _node(
            "save_lead",
            "action",
            "records.upsert",
            {
                "module": "lead",
                "operation": "create",
                "fields": {
                    "interest": "{{pick_interest.reply.label}}",
                    "message": "{{describe_need.reply}}",
                    "status": "new",
                    "customer_id": "{{find_customer.customer.id}}",
                },
            },
            "Save the lead",
            1120,
        ),
        _node(
            "confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "Thanks for reaching out! Someone from our team will get back to you soon."},
            },
            "Send confirmation",
            1400,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "pick_interest"),
        _edge("e3a", "pick_interest", "describe_need", source_handle="sales"),
        _edge("e3b", "pick_interest", "describe_need", source_handle="support"),
        _edge("e3c", "pick_interest", "describe_need", source_handle="partnership"),
        _edge("e4", "describe_need", "save_lead"),
        _edge("e5", "save_lead", "confirmation"),
    ],
}

# ---------------------------------------------------------------------------
# Template 9: Marketing opt-in (consent capture)
# ---------------------------------------------------------------------------

_MARKETING_OPTIN_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "ask_optin",
            "action",
            "flow.confirm",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Would you like to receive occasional offers and updates from us?",
            },
            "Ask for marketing consent",
            560,
        ),
        # `records.upsert` on the "customers" module *replaces* the whole
        # `custom_fields` dict (`customers/service.py::update_customer` sets
        # it outright, it doesn't merge) - fine for a customer with no other
        # custom fields yet or as a demo; a business already tracking other
        # custom fields per customer would want to read-then-merge instead
        # of setting this directly (not something the generic `records.upsert`
        # node does for you today).
        _node(
            "save_optin",
            "action",
            "records.upsert",
            {
                "module": "customers",
                "operation": "update",
                "item_id": "{{find_customer.customer.id}}",
                "fields": {"custom_fields": {"marketing_opt_in": True}},
            },
            "Save opt-in",
            840,
            -100,
        ),
        _node(
            "optin_confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "Great, you're subscribed! You can reply STOP any time to opt out."},
            },
            "Send: subscribed",
            1120,
            -100,
        ),
        _node(
            "optout_confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "No problem, we won't send you promotional messages."},
            },
            "Send: not subscribing",
            840,
            150,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "ask_optin"),
        _edge("e3", "ask_optin", "save_optin", source_handle="yes"),
        _edge("e4", "ask_optin", "optout_confirmation", source_handle="no"),
        _edge("e5", "save_optin", "optin_confirmation"),
    ],
}

# ---------------------------------------------------------------------------
# Template 10: Return / warranty request
# ---------------------------------------------------------------------------

_RETURN_REQUEST_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "pick_reason",
            "action",
            "whatsapp.ask_choice",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Sorry to hear that! What's the reason for your return?",
                "source": {
                    "kind": "static",
                    "options": [
                        {"id": "defective", "label": "Item is defective"},
                        {"id": "wrong_item", "label": "Received wrong item"},
                        {"id": "changed_mind", "label": "Changed my mind"},
                    ],
                },
            },
            "Ask the return reason",
            560,
        ),
        _node(
            "collect_order_id",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "What's the order id for this item?",
            },
            "Collect the order id",
            840,
        ),
        _node(
            "describe_issue",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Please describe the issue in a few words.",
            },
            "Collect a description",
            1120,
        ),
        _node(
            "log_ticket",
            "action",
            "create_ticket",
            {
                "subject": (
                    "Return request ({{pick_reason.reply.label}}) for order "
                    "{{collect_order_id.reply}}: {{describe_issue.reply}}"
                ),
                "customer_id": "{{find_customer.customer.id}}",
            },
            "Log a return ticket",
            1400,
        ),
        _node(
            "confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": (
                    "Thanks! We've logged your return request (ticket {{log_ticket.ticket_id}}) and will "
                    "be in touch with next steps."
                )},
            },
            "Send confirmation",
            1680,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "pick_reason"),
        _edge("e3a", "pick_reason", "collect_order_id", source_handle="defective"),
        _edge("e3b", "pick_reason", "collect_order_id", source_handle="wrong_item"),
        _edge("e3c", "pick_reason", "collect_order_id", source_handle="changed_mind"),
        _edge("e4", "collect_order_id", "describe_issue"),
        _edge("e5", "describe_issue", "log_ticket"),
        _edge("e6", "log_ticket", "confirmation"),
    ],
}

# ---------------------------------------------------------------------------
# Template 11: Appointment cancellation / reschedule
# ---------------------------------------------------------------------------
#
# Reuses `appointment_booking`'s exact `appointment` object-type spec (same
# field keys/types) - a tenant who already has that object type from the
# other template gets no second, mismatched definition (auto-provisioning
# is idempotent by key, see `create_workflow_from_starter_template`).
#
# `pick_appointment` sources its options from the tenant's own `appointment`
# custom object, filtered to this customer - which requires `label_field`
# to reach into `ObjectRecordOut.payload` (a custom object record's own
# fields are nested there, unlike a fixed module's flat `*Out` schema).
# `whatsapp.ask_choice` previously only did a flat `row.get(field)` lookup;
# fixed as part of this work (`nodes/whatsapp_ask_choice.py::_get_field`,
# a purely-additive dotted-path getter) since this is the first template to
# source choices from a tenant-defined object type's own fields rather than
# just its `id`.
_APPOINTMENT_CANCELLATION_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "pick_appointment",
            "action",
            "whatsapp.ask_choice",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Which appointment would you like to cancel?",
                "source": {
                    "kind": "module",
                    "module": "appointment",
                    "filters": {"customer_id": "{{find_customer.customer.id}}"},
                    "label_field": "payload.preferred_time",
                    "value_field": "id",
                    "limit": 10,
                },
            },
            "Ask which appointment",
            560,
        ),
        _node(
            "confirm_cancel",
            "action",
            "flow.confirm",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Cancel your appointment for {{pick_appointment.reply.label}}?",
            },
            "Confirm cancellation",
            840,
        ),
        _node(
            "update_appointment",
            "action",
            "records.upsert",
            {
                "module": "appointment",
                "operation": "update",
                "item_id": "{{pick_appointment.reply.id}}",
                "fields": {"status": "cancelled"},
            },
            "Mark the appointment cancelled",
            1120,
            -100,
        ),
        _node(
            "cancel_confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "Done - your appointment has been cancelled."},
            },
            "Send: cancelled",
            1400,
            -100,
        ),
        _node(
            "keep_confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "No changes made - see you then!"},
            },
            "Send: keeping it",
            1120,
            150,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "pick_appointment"),
        _edge("e3", "pick_appointment", "confirm_cancel"),
        _edge("e4", "confirm_cancel", "update_appointment", source_handle="yes"),
        _edge("e5", "confirm_cancel", "keep_confirmation", source_handle="no"),
        _edge("e6", "update_appointment", "cancel_confirmation"),
    ],
}

# ---------------------------------------------------------------------------
# Template 12: Restaurant table reservation
# ---------------------------------------------------------------------------

_RESERVATION_REQUIRED_OBJECT_TYPES = [
    {
        "key": "reservation",
        "name": "Reservation",
        "icon": "calendar",
        "fields": [
            {"key": "party_size", "label": "Party Size", "field_type": "text", "required": True, "sort_order": 0},
            {
                "key": "preferred_time",
                "label": "Preferred Date/Time",
                "field_type": "text",
                "required": True,
                "sort_order": 1,
            },
            {"key": "notes", "label": "Notes", "field_type": "text", "required": False, "sort_order": 2},
            {
                "key": "status",
                "label": "Status",
                "field_type": "select",
                "options": ["requested", "confirmed", "cancelled"],
                "required": False,
                "sort_order": 3,
            },
        ],
    }
]

_RESTAURANT_RESERVATION_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "collect_party_size",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "How many people will be dining?",
            },
            "Collect party size",
            560,
        ),
        _node(
            "collect_time",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "What date and time would you like to book?",
            },
            "Collect preferred time",
            840,
        ),
        _node(
            "save_reservation",
            "action",
            "records.upsert",
            {
                "module": "reservation",
                "operation": "create",
                "fields": {
                    "party_size": "{{collect_party_size.reply}}",
                    "preferred_time": "{{collect_time.reply}}",
                    "status": "requested",
                    "customer_id": "{{find_customer.customer.id}}",
                },
            },
            "Save the reservation request",
            1120,
        ),
        _node(
            "confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": (
                    "Thanks! We've noted your table for {{collect_party_size.reply}} on "
                    "{{collect_time.reply}} - we'll confirm shortly."
                )},
            },
            "Send booking confirmation",
            1400,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "collect_party_size"),
        _edge("e3", "collect_party_size", "collect_time"),
        _edge("e4", "collect_time", "save_reservation"),
        _edge("e5", "save_reservation", "confirmation"),
    ],
}

# ---------------------------------------------------------------------------
# Template 13: FAQ / business info auto-responder
# ---------------------------------------------------------------------------

_FAQ_AUTORESPONDER_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "pick_topic",
            "action",
            "whatsapp.ask_choice",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Hi! What can we help you with?",
                "source": {
                    "kind": "static",
                    "options": [
                        {"id": "hours", "label": "Business Hours"},
                        {"id": "location", "label": "Location"},
                        {"id": "pricing", "label": "Pricing"},
                        {"id": "other", "label": "Something Else"},
                    ],
                },
            },
            "Ask which topic",
            560,
        ),
        _node(
            "send_hours",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "We're open Monday-Saturday, 9 AM to 7 PM. Closed on Sundays and public holidays."},
            },
            "Send: business hours",
            840,
            -250,
        ),
        _node(
            "send_location",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "You'll find us at [your address here] - reply for directions any time!"},
            },
            "Send: location",
            840,
            -80,
        ),
        _node(
            "send_pricing",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "You can browse our full price list by replying MENU, or ask about a specific item."},
            },
            "Send: pricing",
            840,
            90,
        ),
        _node(
            "describe_question",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Please describe your question and we'll get back to you.",
            },
            "Collect their question",
            840,
            260,
        ),
        _node(
            "log_other_ticket",
            "action",
            "create_ticket",
            {
                "subject": "FAQ: {{describe_question.reply}}",
                "customer_id": "{{find_customer.customer.id}}",
            },
            "Log a ticket for follow-up",
            1120,
            260,
        ),
        _node(
            "other_confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "Thanks - we've noted your question and will get back to you soon."},
            },
            "Send confirmation",
            1400,
            260,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "pick_topic"),
        _edge("e3a", "pick_topic", "send_hours", source_handle="hours"),
        _edge("e3b", "pick_topic", "send_location", source_handle="location"),
        _edge("e3c", "pick_topic", "send_pricing", source_handle="pricing"),
        _edge("e3d", "pick_topic", "describe_question", source_handle="other"),
        _edge("e4", "describe_question", "log_other_ticket"),
        _edge("e5", "log_other_ticket", "other_confirmation"),
    ],
}

# ---------------------------------------------------------------------------
# Template 14: Welcome menu (new vs. returning customer)
# ---------------------------------------------------------------------------

_WELCOME_MENU_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "check_new",
            "condition",
            "condition.field_compare",
            {"field_path": "find_customer.created", "operator": "eq", "value": True},
            "Is this a brand-new customer?",
            560,
        ),
        _node(
            "send_welcome",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "Welcome! We're glad you found us. Reply with ORDER to shop, or SUPPORT if you need help."},
            },
            "Send: welcome (new)",
            840,
            -100,
        ),
        _node(
            "send_welcome_back",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "Welcome back! Reply with ORDER to shop, or SUPPORT if you need help."},
            },
            "Send: welcome back (returning)",
            840,
            100,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "check_new"),
        _edge("e3", "check_new", "send_welcome", source_handle="true"),
        _edge("e4", "check_new", "send_welcome_back", source_handle="false"),
    ],
}

# ---------------------------------------------------------------------------
# Template 15: Restaurant ordering (dine-in vs. delivery)
# ---------------------------------------------------------------------------

_RESTAURANT_CART_ORDERING_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "whatsapp.message_received", {}, "New WhatsApp message", 0),
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            280,
        ),
        _node(
            "ask_for_cart",
            "action",
            "whatsapp.ask_for_cart",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "catalog_id": _PLACEHOLDER_CATALOG_ID,
                "body_text": "Hi! Browse our menu below and add whatever you'd like, then tap send.",
                "module": "products",
                "filters": {},
                "limit": 30,
                "section_title": "Our Menu",
            },
            "Ask customer to build an order",
            560,
        ),
        _node(
            "ask_dine_option",
            "action",
            "whatsapp.ask_choice",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Will this be dine-in or delivery?",
                "source": {
                    "kind": "static",
                    "options": [
                        {"id": "dine_in", "label": "Dine In"},
                        {"id": "delivery", "label": "Delivery"},
                    ],
                },
            },
            "Ask dine-in or delivery",
            840,
        ),
        _node(
            "collect_address",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "What's the delivery address?",
            },
            "Collect delivery address",
            1120,
            150,
        ),
        _node(
            "pick_payment",
            "action",
            "whatsapp.ask_choice",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "How would you like to pay?",
                "source": {
                    "kind": "static",
                    "options": [
                        {"id": "cod", "label": "Cash on Delivery"},
                        {"id": "prepaid", "label": "Pay Online"},
                    ],
                },
            },
            "Ask how they'll pay",
            1400,
        ),
        _node(
            "create_order_cod",
            "action",
            "orders.create_from_cart",
            {
                "customer_id": "{{find_customer.customer.id}}",
                "cart_items_path": "ask_for_cart.reply.product_items",
                "currency": "INR",
                "payment_method": "cod",
            },
            "Create the order (cash on delivery)",
            1680,
            -150,
        ),
        _node(
            "create_order_prepaid",
            "action",
            "orders.create_from_cart",
            {
                "customer_id": "{{find_customer.customer.id}}",
                "cart_items_path": "ask_for_cart.reply.product_items",
                "currency": "INR",
                "payment_method": "prepaid",
            },
            "Create the order (online payment)",
            1680,
            50,
        ),
        _node(
            "cod_confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "Thanks! Your order ({{create_order_cod.item_count}} item(s)) is confirmed, paying cash."},
            },
            "Send: cash-on-delivery confirmation",
            1960,
            -150,
        ),
        _node(
            "send_payment_link",
            "action",
            "payments.send_razorpay_link",
            {
                "razorpay_connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "whatsapp_connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "amount": "{{create_order_prepaid.total_amount}}",
                "currency": "INR",
                "order_id": "{{create_order_prepaid.order_id}}",
                "customer_contact": "{{trigger.from}}",
            },
            "Send payment link",
            1960,
            50,
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "find_customer"),
        _edge("e2", "find_customer", "ask_for_cart"),
        _edge("e3", "ask_for_cart", "ask_dine_option"),
        _edge("e4a", "ask_dine_option", "pick_payment", source_handle="dine_in"),
        _edge("e4b", "ask_dine_option", "collect_address", source_handle="delivery"),
        _edge("e5", "collect_address", "pick_payment"),
        _edge("e6", "pick_payment", "create_order_cod", source_handle="cod"),
        _edge("e7", "pick_payment", "create_order_prepaid", source_handle="prepaid"),
        _edge("e8", "create_order_cod", "cod_confirmation"),
        _edge("e9", "create_order_prepaid", "send_payment_link"),
    ],
}

# ---------------------------------------------------------------------------
# Template 16: Broadcast a message (recurring/scheduled bulk send)
# ---------------------------------------------------------------------------
#
# Pairs with the `WorkflowSchedule` CRUD API (recurring/scheduled bulk-send
# support for "Broadcast"-purpose workflows) - `broadcast.scheduled_send`
# fires once per configured schedule run with `recipients: list[str]`
# already resolved server-side (static phone list or a module lookup), so
# this graph's only job is to fan that list out to one `whatsapp.
# send_message` per recipient via an ordinary `flow.loop` - no per-recipient
# branching or special-casing needed, same "container node does the
# fan-out, the body is one plain node" shape `flow.loop`'s other templates
# use for a dynamic-size list (e.g. `orders.create_from_cart`'s own cart
# loop). The trigger itself has no meaningful author-facing config (see
# its own `output_schema`), so its `config` stays `{}` like every other
# trigger node in this file.
_BROADCAST_MESSAGE_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "broadcast.scheduled_send", {}, "Scheduled broadcast", 0),
        _node(
            "loop",
            "action",
            "flow.loop",
            {"items_path": "{{trigger.recipients}}"},
            "For each recipient",
            280,
        ),
        _node(
            "send_message",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{loop.item}}",
                "content": {"content_type": "text", "body": "Hello {{loop.item}}!"},
            },
            "Send the message",
            280,
            100,
            parent_id="loop",
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "loop"),
    ],
}

# ---------------------------------------------------------------------------
# Marketing template broadcast (approved WhatsApp template, image header + CTA
# button) - sent to a recipient list drawn from `{{trigger.recipients}}`,
# right now or on a schedule via `broadcast.scheduled_send`. WhatsApp policy
# requires a pre-approved Marketing template (not a plain session message)
# for any customer without an active 24-hour session, which a scheduled
# broadcast to an arbitrary list can never assume - see
# `whatsapp.send_message`'s `TemplateContent` for the full set of optional
# template fields (`header_media_type`/`header_media_url`/`header_media_id`
# for a media header, mutually exclusive with a text `header_variable`, plus
# `button_url_params` to fill in a dynamic URL button already defined on the
# approved template itself, not a way to author new buttons).
# ---------------------------------------------------------------------------

_MARKETING_TEMPLATE_BROADCAST_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "broadcast.scheduled_send", {}, "Scheduled broadcast", 0),
        _node(
            "loop",
            "action",
            "flow.loop",
            {"items_path": "{{trigger.recipients}}"},
            "For each recipient",
            280,
        ),
        _node(
            "send_broadcast",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{loop.item}}",
                "content": {
                    "content_type": "template",
                    "template_name": _PLACEHOLDER_TEMPLATE_NAME,
                    "language_code": "en_US",
                    "header_media_type": "image",
                    "header_media_url": "https://example.com/promo-banner.jpg",
                    "body_variables": [],
                    "button_url_params": ["{{loop.item}}"],
                },
            },
            "Send the marketing template",
            280,
            100,
            parent_id="loop",
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "loop"),
    ],
}

# ---------------------------------------------------------------------------
# Re-engagement blast (plain session text) - sent to a recipient list drawn
# from `{{trigger.recipients}}`, right now or on a schedule via
# `broadcast.scheduled_send`. Unlike the Marketing Template Broadcast above,
# this is a plain `content_type: "text"` message, which WhatsApp only
# delivers inside an already-open 24-hour customer service session (e.g.
# shortly after a support conversation) - it is NOT a substitute for an
# approved template when reaching customers outside that window.
# ---------------------------------------------------------------------------

_REENGAGEMENT_BLAST_GRAPH = {
    "nodes": [
        _node("trigger", "trigger", "broadcast.scheduled_send", {}, "Scheduled broadcast", 0),
        _node(
            "loop",
            "action",
            "flow.loop",
            {"items_path": "{{trigger.recipients}}"},
            "For each recipient",
            280,
        ),
        _node(
            "send_broadcast",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{loop.item}}",
                "content": {
                    "content_type": "text",
                    "body": "Hi! We miss you - here's something special just for you. Reply STOP to opt out.",
                },
            },
            "Send the re-engagement message",
            280,
            100,
            parent_id="loop",
        ),
    ],
    "edges": [
        _edge("e1", "trigger", "loop"),
    ],
}

TEMPLATES: list[dict] = [
    {
        "key": "whatsapp_ordering",
        "name": "WhatsApp Guided Ordering",
        "description": (
            "Greets the customer, shows your product catalog as a real WhatsApp cart they can add any "
            "number of items to, applies a coupon code, confirms the order, collects a delivery address, "
            "takes cash-on-delivery or an online Razorpay payment, and confirms once payment is received. "
            "Requires a Meta Commerce Catalog connected to your WhatsApp Business Account (set up on "
            "Meta's side) with each product's retailer id set to match its id in this system - after "
            "starting from this template, fill in your own catalog id in the 'Ask customer to build a "
            "cart' node, same as any other connector placeholder. Every step is an ordinary node you can "
            "edit, remove, or add more of."
        ),
        "category": "Ecommerce",
        "icon": "shopping-cart",
        "graph_json": _ORDERING_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "appointment_booking",
        "name": "Appointment Booking",
        "description": (
            "Greets the customer, lets them pick a service, asks for a preferred time, and saves the "
            "request as an 'Appointment' record you can view and manage - proves you can build a guided "
            "flow around a business object you define yourself, not just the built-in modules."
        ),
        "category": "Appointments",
        "icon": "calendar",
        "graph_json": _APPOINTMENT_GRAPH,
        "required_object_types": _APPOINTMENT_REQUIRED_OBJECT_TYPES,
        "is_active": True,
    },
    {
        "key": "whatsapp_support_ticket",
        "name": "WhatsApp Support Ticket",
        "description": (
            "Greets the customer, asks what kind of issue they have, collects a short description, and "
            "logs a support ticket linked to their customer record - with a confirmation reply including "
            "the ticket reference."
        ),
        "category": "Support",
        "icon": "life-buoy",
        "graph_json": _SUPPORT_TICKET_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "order_confirmation_broadcast",
        "name": "Order Confirmation Broadcast",
        "description": (
            "Fires whenever a new order is created - from checkout, another workflow, or anywhere else - "
            "looks up the customer's WhatsApp number, and sends them an order confirmation automatically. "
            "Requires an approved WhatsApp Utility template (set one up in WhatsApp Settings, then fill "
            "in its name on the send-confirmation node) since this flow doesn't start from a WhatsApp "
            "message and can't assume an open 24-hour session."
        ),
        "category": "Ecommerce",
        "icon": "bell",
        "graph_json": _ORDER_CONFIRMATION_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "post_purchase_feedback",
        "name": "Post-Purchase Feedback Survey",
        "description": (
            "Fires whenever a new order is created, asks the customer to rate their experience (1-5) and "
            "leave an optional comment, and saves the response as a 'Feedback' record you can review - "
            "another example of building around your own custom business object. Requires an approved "
            "WhatsApp Utility template for the initial rating request, same reason as Order Confirmation "
            "Broadcast - fill in the template name on the ask-for-a-rating node before publishing."
        ),
        "category": "Ecommerce",
        "icon": "star",
        "graph_json": _FEEDBACK_GRAPH,
        "required_object_types": _FEEDBACK_REQUIRED_OBJECT_TYPES,
        "is_active": True,
    },
    {
        "key": "order_status_check",
        "name": "Order Status Check",
        "description": (
            "Lets a customer self-serve 'where's my order?' - asks for their order id, looks it up (with "
            "a graceful 'couldn't find that' reply if it's invalid or not theirs), and reports the status "
            "and total. Demonstrates flow.try_catch for a friendly failure path."
        ),
        "category": "Ecommerce",
        "icon": "shopping-cart",
        "graph_json": _ORDER_STATUS_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "product_availability_check",
        "name": "Product Availability Check",
        "description": (
            "Lets a customer ask about a specific product and get back its current price and whether "
            "it's in stock, straight from your live catalog."
        ),
        "category": "Ecommerce",
        "icon": "package",
        "graph_json": _PRODUCT_AVAILABILITY_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "lead_capture",
        "name": "Lead Capture / Contact Us",
        "description": (
            "Greets a new WhatsApp contact, asks what they're interested in, collects a short message, "
            "and saves it as a 'Lead' record for your sales team to follow up on."
        ),
        "category": "Sales",
        "icon": "users",
        "graph_json": _LEAD_CAPTURE_GRAPH,
        "required_object_types": _LEAD_REQUIRED_OBJECT_TYPES,
        "is_active": True,
    },
    {
        "key": "marketing_optin",
        "name": "Marketing Opt-in",
        "description": (
            "Asks a customer for consent to receive future offers/updates and records their answer - "
            "useful before sending any Marketing-category WhatsApp template messages."
        ),
        "category": "Marketing",
        "icon": "bell",
        "graph_json": _MARKETING_OPTIN_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "marketing_template_broadcast",
        "name": "Marketing Template Broadcast",
        "description": (
            "Send an approved WhatsApp marketing template - with an image header and a call-to-action "
            "button - to a list of customers, right now or on a schedule."
        ),
        "category": "Marketing",
        "icon": "megaphone",
        "graph_json": _MARKETING_TEMPLATE_BROADCAST_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "reengagement_blast",
        "name": "Re-engagement Blast",
        "description": (
            "Send a plain text message to a list of customers you've recently interacted with (within "
            "WhatsApp's active session window), right now or on a schedule."
        ),
        "category": "Marketing",
        "icon": "megaphone",
        "graph_json": _REENGAGEMENT_BLAST_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "return_request",
        "name": "Return / Warranty Request",
        "description": (
            "Asks why a customer wants to return an item, collects the order id and a description, and "
            "logs a support ticket so your team can process the return."
        ),
        "category": "Support",
        "icon": "life-buoy",
        "graph_json": _RETURN_REQUEST_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "appointment_cancellation",
        "name": "Appointment Cancellation",
        "description": (
            "Lets a customer pick one of their own upcoming appointments and cancel it, updating the same "
            "'Appointment' record the Appointment Booking template creates - start that template first if "
            "you haven't already, or this one will provision the same object type for you automatically."
        ),
        "category": "Appointments",
        "icon": "calendar",
        "graph_json": _APPOINTMENT_CANCELLATION_GRAPH,
        "required_object_types": _APPOINTMENT_REQUIRED_OBJECT_TYPES,
        "is_active": True,
    },
    {
        "key": "restaurant_reservation",
        "name": "Restaurant Table Reservation",
        "description": (
            "Asks for party size and preferred date/time, and saves the request as a 'Reservation' record "
            "you can review and confirm."
        ),
        "category": "Appointments",
        "icon": "calendar",
        "graph_json": _RESTAURANT_RESERVATION_GRAPH,
        "required_object_types": _RESERVATION_REQUIRED_OBJECT_TYPES,
        "is_active": True,
    },
    {
        "key": "faq_autoresponder",
        "name": "FAQ / Business Info Auto-responder",
        "description": (
            "Offers a quick menu of common questions (hours, location, pricing) with an instant canned "
            "reply for each, and falls back to logging a support ticket for anything else."
        ),
        "category": "Support",
        "icon": "life-buoy",
        "graph_json": _FAQ_AUTORESPONDER_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "welcome_menu",
        "name": "Welcome Menu (New vs. Returning Customer)",
        "description": (
            "A simple entry-point pattern: greets a first-time WhatsApp contact differently from a "
            "returning one, then points them at your other flows (ORDER, SUPPORT, ...)."
        ),
        "category": "Customers",
        "icon": "users",
        "graph_json": _WELCOME_MENU_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "restaurant_cart_ordering",
        "name": "Restaurant Ordering (Dine-in or Delivery)",
        "description": (
            "A menu-based cart order (via WhatsApp's Commerce Catalog, same as WhatsApp Guided Ordering) "
            "that asks dine-in vs. delivery first and only collects an address for delivery, then takes "
            "cash or online payment."
        ),
        "category": "Ecommerce",
        "icon": "shopping-cart",
        "graph_json": _RESTAURANT_CART_ORDERING_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "broadcast_message",
        "name": "Broadcast a Message",
        "description": "Send a message to a list of customers, right now or on a schedule.",
        "category": "Marketing",
        "icon": "megaphone",
        "graph_json": _BROADCAST_MESSAGE_GRAPH,
        "required_object_types": None,
        "is_active": True,
    },
]


async def seed() -> None:
    async with async_session_factory() as session:
        existing_by_key = {t.key: t for t in await admin_service.list_workflow_starter_templates(session)}
        for spec in TEMPLATES:
            existing = existing_by_key.get(spec["key"])
            if existing is not None:
                await admin_service.update_workflow_starter_template(
                    session,
                    existing.id,
                    name=spec["name"],
                    description=spec["description"],
                    category=spec["category"],
                    icon=spec["icon"],
                    graph_json=spec["graph_json"],
                    required_object_types=spec["required_object_types"],
                    is_active=spec["is_active"],
                )
                print(f"updated: {spec['key']}")
                continue
            await admin_service.create_workflow_starter_template(
                session,
                key=spec["key"],
                name=spec["name"],
                description=spec["description"],
                category=spec["category"],
                icon=spec["icon"],
                graph_json=spec["graph_json"],
                required_object_types=spec["required_object_types"],
                is_active=spec["is_active"],
            )
            print(f"created: {spec['key']}")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
