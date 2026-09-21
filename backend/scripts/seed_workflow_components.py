"""Seed the `workflow_components` catalog (composable-workflow-builder
redesign, follow-up feature) - small, reusable fragments (a handful of
nodes+edges) a tenant inserts into a workflow they're ALREADY editing,
distinct from `workflow_starter_templates`' whole-new-workflow shape (see
`modules/admin/models.py::WorkflowComponent`'s docstring for the full
design). Every fragment here is built from real, already-registered node
types - no engine change was needed for this feature.

Fragments are deliberately left with some wiring dangling on purpose (an
unwired `flow.confirm`/`condition.field_compare` handle, or a config value
referencing a placeholder token like `"{{YOUR_ORDER_NODE_ID.order_id}}"`)
for the author to wire into their own workflow after inserting it - the
same "placeholder the author fills in" mental model
`workflow_starter_templates`' placeholder `connector_instance_id`s already
use. `CardNode.tsx`'s existing unconnected-handle styling and the existing
publish-time validation panel already surface exactly what's still
dangling, so no new validation concept exists for this.

Idempotent - matches on `key`, updates in place, safe to re-run after
editing the fragments below.

Usage:
    python scripts/seed_workflow_components.py
"""

from __future__ import annotations

import asyncio

from fusionflow.db.session import async_session_factory
from fusionflow.modules.admin import service as admin_service

#: Deliberately not a real connector - the author picks their own connected
#: instance after inserting the fragment (same convention
#: `seed_workflow_starter_templates.py` already establishes).
_PLACEHOLDER_CONNECTOR_ID = "00000000-0000-0000-0000-000000000000"

#: Deliberately not a real approved template name - see
#: `seed_workflow_starter_templates.py`'s identical constant for why this
#: can't just be an empty string (`whatsapp.ask_via_template`'s
#: `template_name` has `min_length=1`).
_PLACEHOLDER_TEMPLATE_NAME = "replace_with_your_approved_template_name"


def _node(node_id: str, kind: str, node_type: str, config: dict, label: str, x: float, y: float = 0) -> dict:
    return {
        "id": node_id,
        "type": kind,
        "data": {"nodeType": node_type, "config": config, "label": label},
        "position": {"x": x, "y": y},
    }


def _edge(edge_id: str, source: str, target: str, source_handle: str | None = None) -> dict:
    edge: dict = {"id": edge_id, "source": source, "target": target}
    if source_handle is not None:
        edge["sourceHandle"] = source_handle
    return edge


# ---------------------------------------------------------------------------
# Component 1: Coupon Code Check
# ---------------------------------------------------------------------------
# Three dangling exits for the author to wire into their own checkout: a
# valid coupon (`check_coupon`'s "true" handle), no coupon at all
# (`ask_coupon`'s "no" handle), and an invalid one after telling the
# customer (`coupon_invalid`, a leaf). All three are meant to converge back
# into wherever the author's own order-confirmation step is.

_COUPON_CODE_CHECK_FRAGMENT = {
    "nodes": [
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
            280,
            -120,
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
            560,
            -120,
        ),
        _node(
            "check_coupon",
            "condition",
            "condition.field_compare",
            {"field_path": "lookup_coupon.count", "operator": "gt", "value": 0},
            "Is the coupon valid?",
            840,
            -120,
        ),
        _node(
            "coupon_invalid",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "That coupon code isn't valid or has expired — continuing without a discount."},
            },
            "Send: coupon not valid",
            1120,
            0,
        ),
    ],
    "edges": [
        _edge("e1", "ask_coupon", "collect_coupon", source_handle="yes"),
        # `ask_coupon`'s "no" handle is left unwired on purpose - the
        # author wires it straight to their own checkout continuation.
        _edge("e2", "collect_coupon", "lookup_coupon"),
        _edge("e3", "lookup_coupon", "check_coupon"),
        # `check_coupon`'s "true" handle is left unwired on purpose - same
        # destination as `ask_coupon`'s "no" handle above.
        _edge("e4", "check_coupon", "coupon_invalid", source_handle="false"),
        # `coupon_invalid` is a leaf - wire it onward to the same
        # continuation too, once the customer's been told.
    ],
}

# ---------------------------------------------------------------------------
# Component 2: Payment Collection (COD / Razorpay)
# ---------------------------------------------------------------------------
# The `"cod"` handle is a dangling leaf (nothing further needed - the order
# was already created with `payment_method="cod"`). The `"prepaid"` path
# needs an order id/amount to send a payment link for - `send_payment_link`
# references the placeholder token `YOUR_ORDER_NODE_ID`, which the author
# must replace with whichever order-creation node id exists in their own
# workflow (e.g. `{{create_order.order_id}}`).

_PAYMENT_COLLECTION_FRAGMENT = {
    "nodes": [
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
            0,
        ),
        _node(
            "send_payment_link",
            "action",
            "payments.send_razorpay_link",
            {
                "razorpay_connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "whatsapp_connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                # Placeholders the author MUST replace with the actual
                # node id of whichever order-creation step already exists
                # in their own workflow (e.g. "create_order",
                # "create_order_prepaid", ...) - this fragment has no way
                # to know that id in advance.
                "amount": "{{YOUR_ORDER_NODE_ID.total_amount}}",
                "order_id": "{{YOUR_ORDER_NODE_ID.order_id}}",
                "currency": "INR",
                "customer_contact": "{{trigger.from}}",
            },
            "Send payment link (replace YOUR_ORDER_NODE_ID)",
            280,
            120,
        ),
    ],
    "edges": [
        # `pick_payment`'s "cod" handle is left unwired on purpose - a leaf,
        # nothing further needed once the order is already created as cod.
        _edge("e1", "pick_payment", "send_payment_link", source_handle="prepaid"),
    ],
}

# ---------------------------------------------------------------------------
# Component 3: Cart Selection (WhatsApp Catalog)
# ---------------------------------------------------------------------------
# A single, pre-configured node - `catalog_id`/`connector_instance_id` stay
# placeholders (a global component can't know the tenant's real values).

_CART_SELECTION_FRAGMENT = {
    "nodes": [
        _node(
            "ask_for_cart",
            "action",
            "whatsapp.ask_for_cart",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "catalog_id": "REPLACE_WITH_YOUR_META_CATALOG_ID",
                "body_text": "Browse our catalog below, add whatever you'd like to your cart, then tap send.",
                "module": "products",
                "filters": {},
                "limit": 30,
                "section_title": "Products",
            },
            "Ask the customer to build a cart",
            0,
        ),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 4: Support Ticket Intake
# ---------------------------------------------------------------------------
# `pick_category` is a static `whatsapp.ask_choice` - every one of its 3
# options needs its own edge to `describe_issue`, even though all 3 lead to
# the exact same next node (the compile-time branch expansion gives each
# option its own handle; an edge with no/other handle would land on the
# "default" handle instead, which only fires when nothing matches).

_SUPPORT_TICKET_INTAKE_FRAGMENT = {
    "nodes": [
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
            "Ask what they need help with",
            0,
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
            280,
        ),
        _node(
            "log_ticket",
            "action",
            "create_ticket",
            {
                "subject": "{{pick_category.reply.label}}: {{describe_issue.reply}}",
                # Placeholder the author must replace with whichever
                # customer-identifying node id exists in their own workflow
                # (e.g. a `whatsapp.find_or_create_customer` node's id).
                "customer_id": "{{YOUR_CUSTOMER_NODE_ID.customer.id}}",
            },
            "Log a support ticket (replace YOUR_CUSTOMER_NODE_ID)",
            560,
        ),
        _node(
            "confirmation",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "Thanks! We've logged your request (ticket {{log_ticket.ticket_id}}) and will get back to you soon."},
            },
            "Send confirmation",
            840,
        ),
    ],
    "edges": [
        _edge("e1", "pick_category", "describe_issue", source_handle="order_issue"),
        _edge("e2", "pick_category", "describe_issue", source_handle="general"),
        _edge("e3", "pick_category", "describe_issue", source_handle="complaint"),
        _edge("e4", "describe_issue", "log_ticket"),
        _edge("e5", "log_ticket", "confirmation"),
    ],
}

# ---------------------------------------------------------------------------
# Component 5: Post-Purchase Rating Request
# ---------------------------------------------------------------------------
# Same "feedback" custom object type `post_purchase_feedback`'s starter
# template already declares (kept byte-identical in shape so both stay in
# sync) - `provision_component` auto-creates it for the tenant on insert if
# they don't already have one under that key.

_POST_PURCHASE_RATING_REQUIRED_OBJECT_TYPES = [
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

_POST_PURCHASE_RATING_FRAGMENT = {
    "nodes": [
        _node(
            "ask_rating",
            "action",
            "whatsapp.ask_via_template",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "template_name": _PLACEHOLDER_TEMPLATE_NAME,
                "language_code": "en_US",
                # Placeholder - replace with wherever the customer's name
                # is available in your own workflow.
                "body_variables": ["{{YOUR_CUSTOMER_NAME_PATH}}"],
            },
            "Ask for a rating (replace template + name path)",
            0,
        ),
        _node(
            "collect_comment",
            "action",
            "whatsapp.collect_text",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "question": "Thanks! Any comments you'd like to share? (Reply 'none' if not.)",
            },
            "Collect a comment",
            280,
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
                    # Placeholder - replace with whichever customer/order
                    # node ids exist in your own workflow.
                    "customer_id": "{{YOUR_CUSTOMER_NODE_ID.customer.id}}",
                },
            },
            "Save the feedback (replace YOUR_CUSTOMER_NODE_ID)",
            560,
        ),
        _node(
            "thank_you",
            "action",
            "whatsapp.send_message",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "to": "{{trigger.from}}",
                "content": {"content_type": "text", "body": "Thank you for your feedback — we really appreciate it!"},
            },
            "Send thank-you",
            840,
        ),
    ],
    "edges": [
        _edge("e1", "ask_rating", "collect_comment"),
        _edge("e2", "collect_comment", "save_feedback"),
        _edge("e3", "save_feedback", "thank_you"),
    ],
}

# ---------------------------------------------------------------------------
# Component 6: New vs. Returning Customer Branch
# ---------------------------------------------------------------------------
# Both branches are dangling leaves - the author wires "true" (new
# customer) to their own onboarding/welcome steps and "false" (returning)
# to their own main-menu steps.

_NEW_VS_RETURNING_CUSTOMER_FRAGMENT = {
    "nodes": [
        _node(
            "find_customer",
            "action",
            "whatsapp.find_or_create_customer",
            {"phone": "{{trigger.from}}"},
            "Identify the customer",
            0,
        ),
        _node(
            "check_new",
            "condition",
            "condition.field_compare",
            {"field_path": "find_customer.created", "operator": "eq", "value": True},
            "Is this a new customer?",
            280,
        ),
    ],
    "edges": [
        _edge("e1", "find_customer", "check_new"),
        # Both "true" (new) and "false" (returning) are left unwired on
        # purpose - wire each to your own welcome vs. main-menu steps.
    ],
}

# ---------------------------------------------------------------------------
# Component 7: Notify on Payment Received (trigger-rooted)
# ---------------------------------------------------------------------------
# Includes its own trigger - inserting this into an existing workflow adds
# a second, independent entry point (already supported with zero engine
# changes - `whatsapp_ordering`'s starter template has used exactly this
# "a second top-level trigger in the same graph" shape since it was built).

_NOTIFY_ON_PAYMENT_RECEIVED_FRAGMENT = {
    "nodes": [
        _node("payment_trigger", "trigger", "payment.captured", {}, "Payment received", 0),
        _node(
            "get_customer_for_payment",
            "action",
            "records.query",
            {"module": "customers", "operation": "get", "item_id": "{{payment_trigger.customer_id}}"},
            "Look up who paid",
            280,
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
            "Send payment confirmation",
            560,
        ),
    ],
    "edges": [
        _edge("e1", "payment_trigger", "get_customer_for_payment"),
        _edge("e2", "get_customer_for_payment", "payment_confirmation"),
    ],
}

COMPONENTS: list[dict] = [
    {
        "key": "coupon_code_check",
        "name": "Coupon Code Check",
        "description": "Asks if the customer has a coupon code, validates it against your active coupons, and "
        "continues either way - wire its 3 loose ends into your own checkout flow.",
        "category": "Ecommerce",
        "icon": "ticket-percent",
        "graph_fragment": _COUPON_CODE_CHECK_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "payment_collection",
        "name": "Payment Collection (COD / Razorpay)",
        "description": "Asks how the customer wants to pay and sends a Razorpay payment link for online payment. "
        "Replace the YOUR_ORDER_NODE_ID placeholder with your own order-creation node's id.",
        "category": "Payments",
        "icon": "credit-card",
        "graph_fragment": _PAYMENT_COLLECTION_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "cart_selection",
        "name": "Cart Selection (WhatsApp Catalog)",
        "description": "Lets the customer browse your product catalog natively inside WhatsApp and submit a "
        "multi-item cart in one message.",
        "category": "Ecommerce",
        "icon": "shopping-cart",
        "graph_fragment": _CART_SELECTION_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "support_ticket_intake",
        "name": "Support Ticket Intake",
        "description": "Picks an issue category, collects a description, and logs a support ticket. Replace the "
        "YOUR_CUSTOMER_NODE_ID placeholder with your own customer-lookup node's id.",
        "category": "Support",
        "icon": "life-buoy",
        "graph_fragment": _SUPPORT_TICKET_INTAKE_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "post_purchase_rating",
        "name": "Post-Purchase Rating Request",
        "description": "Sends an approved template asking the customer to rate their experience 1-5, collects an "
        "optional comment, and saves it as a Feedback record.",
        "category": "Ecommerce",
        "icon": "star",
        "graph_fragment": _POST_PURCHASE_RATING_FRAGMENT,
        "required_object_types": _POST_PURCHASE_RATING_REQUIRED_OBJECT_TYPES,
        "is_active": True,
    },
    {
        "key": "new_vs_returning_customer",
        "name": "New vs. Returning Customer Branch",
        "description": "Identifies the WhatsApp sender as a customer and branches on whether they were just "
        "created - a common 'main menu' hub pattern.",
        "category": "Customers",
        "icon": "users",
        "graph_fragment": _NEW_VS_RETURNING_CUSTOMER_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "notify_on_payment_received",
        "name": "Notify on Payment Received",
        "description": "Adds a second entry point to your workflow: when Razorpay confirms a payment, look up who "
        "paid and send them a WhatsApp confirmation.",
        "category": "Payments",
        "icon": "bell",
        "graph_fragment": _NOTIFY_ON_PAYMENT_RECEIVED_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
]


async def seed() -> None:
    async with async_session_factory() as session:
        existing_by_key = {c.key: c for c in await admin_service.list_workflow_components(session)}
        for spec in COMPONENTS:
            existing = existing_by_key.get(spec["key"])
            if existing is not None:
                await admin_service.update_workflow_component(
                    session,
                    existing.id,
                    name=spec["name"],
                    description=spec["description"],
                    category=spec["category"],
                    icon=spec["icon"],
                    graph_fragment=spec["graph_fragment"],
                    required_object_types=spec["required_object_types"],
                    is_active=spec["is_active"],
                )
                print(f"updated: {spec['key']}")
                continue
            await admin_service.create_workflow_component(
                session,
                key=spec["key"],
                name=spec["name"],
                description=spec["description"],
                category=spec["category"],
                icon=spec["icon"],
                graph_fragment=spec["graph_fragment"],
                required_object_types=spec["required_object_types"],
                is_active=spec["is_active"],
            )
            print(f"created: {spec['key']}")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
