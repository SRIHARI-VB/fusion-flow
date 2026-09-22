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

# ---------------------------------------------------------------------------
# Component 8: Instagram - Reply to Comment
# ---------------------------------------------------------------------------
# A single, dangling-input action - no trigger of its own. The author wires
# their own trigger/condition (typically `instagram.comment_received`, maybe
# behind a keyword gate) into this node's only input, same "whichever
# trigger fired this workflow" convention `_COUPON_CODE_CHECK_FRAGMENT`'s
# `{{trigger.from}}` already uses.

_INSTAGRAM_REPLY_TO_COMMENT_FRAGMENT = {
    "nodes": [
        _node(
            "reply_to_comment",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "reply_to_comment",
                "params": {
                    "comment_id": "{{trigger.comment_id}}",
                    "text": "Thanks so much for your comment! We'll get back to you shortly.",
                },
            },
            "Reply to the comment",
            0,
        ),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 9: Instagram - Private Reply to Comment
# ---------------------------------------------------------------------------
# `send_private_reply` addresses the DM by `comment_id`, not the commenter's
# user id - works even on a first-time commenter with no open 24h messaging
# window (see `instagram/adapter.py::send_private_reply`'s docstring).

_INSTAGRAM_PRIVATE_REPLY_TO_COMMENT_FRAGMENT = {
    "nodes": [
        _node(
            "send_private_reply",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "send_private_reply",
                "params": {
                    "comment_id": "{{trigger.comment_id}}",
                    "text": "Thanks for your comment! We've sent you a DM with more details.",
                },
            },
            "Send a private reply",
            0,
        ),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 10: Instagram - Reply to Direct Message
# ---------------------------------------------------------------------------

_INSTAGRAM_REPLY_TO_DM_FRAGMENT = {
    "nodes": [
        _node(
            "reply_to_dm",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "send_direct_message",
                "params": {
                    "recipient_id": "{{trigger.from}}",
                    "text": "Thanks for reaching out! How can we help you today?",
                },
            },
            "Reply with a direct message",
            0,
        ),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 11: Instagram - React to Message
# ---------------------------------------------------------------------------

_INSTAGRAM_REACT_TO_MESSAGE_FRAGMENT = {
    "nodes": [
        _node(
            "react_to_message",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "react_to_message",
                "params": {
                    "recipient_id": "{{trigger.from}}",
                    "message_id": "{{trigger.message_id}}",
                    "reaction": "love",
                },
            },
            "React with a heart",
            0,
        ),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 12: Instagram - Send a Media Reply
# ---------------------------------------------------------------------------

_INSTAGRAM_SEND_MEDIA_REPLY_FRAGMENT = {
    "nodes": [
        _node(
            "send_media_reply",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "send_media_message",
                "params": {
                    "recipient_id": "{{trigger.from}}",
                    "media_url": "https://example.com/replace-with-your-media-url.jpg",
                    "media_type": "image",
                },
            },
            "Send a media reply (replace media_url)",
            0,
        ),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 13: Instagram - Send a Button Menu
# ---------------------------------------------------------------------------
# Up to 3 tappable buttons (Meta's own limit on a Button Template - see
# `instagram/adapter.py::send_button_template`'s docstring). A tap comes
# back through `instagram.postback_received`'s `payload` field, ready for a
# `condition.field_compare` to branch on.

_INSTAGRAM_SEND_BUTTON_MENU_FRAGMENT = {
    "nodes": [
        _node(
            "send_button_menu",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "send_button_template",
                "params": {
                    "recipient_id": "{{trigger.from}}",
                    "text": "What would you like to do next?",
                    "buttons": [
                        {"title": "See our products", "payload": "SEE_PRODUCTS"},
                        {"title": "Talk to a person", "payload": "TALK_TO_HUMAN"},
                        {"title": "Track my order", "payload": "TRACK_ORDER"},
                    ],
                },
            },
            "Send a button menu",
            0,
        ),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 14: Instagram - Thank a Story Reply
# ---------------------------------------------------------------------------
# Includes its own trigger - a Story reply is a distinct entry point, not
# something an author is likely to already have wired elsewhere in their
# workflow (same "second top-level trigger" shape as
# `_NOTIFY_ON_PAYMENT_RECEIVED_FRAGMENT`).

_INSTAGRAM_THANK_STORY_REPLY_FRAGMENT = {
    "nodes": [
        _node("story_reply_trigger", "trigger", "instagram.story_reply_received", {}, "Story reply received", 0),
        _node(
            "thank_you_dm",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "send_direct_message",
                "params": {
                    "recipient_id": "{{story_reply_trigger.from}}",
                    "text": "Thanks so much for replying to our story! We loved hearing from you.",
                },
            },
            "Send a thank-you DM",
            280,
        ),
    ],
    "edges": [
        _edge("e1", "story_reply_trigger", "thank_you_dm"),
    ],
}

# ---------------------------------------------------------------------------
# Component 15: Instagram - Thank a Mention
# ---------------------------------------------------------------------------
# `instagram.mention_received`'s `comment_id` is only populated for a
# mention left in a comment - a mention in a post/reel CAPTION has no
# comment to reply to, and `reply_to_comment` will fail at run time for
# that case (see `_resolve_mention_details`'s docstring on the connector
# adapter). Swap the action for `send_direct_message` to
# `{{mention_trigger.from_id}}` instead if you expect caption mentions.

_INSTAGRAM_THANK_MENTION_FRAGMENT = {
    "nodes": [
        _node("mention_trigger", "trigger", "instagram.mention_received", {}, "Mention received", 0),
        _node(
            "thank_you_reply",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "reply_to_comment",
                "params": {
                    "comment_id": "{{mention_trigger.comment_id}}",
                    "text": "Thank you for the shoutout! We really appreciate it.",
                },
            },
            "Reply thanking them (comment mentions only - see above)",
            280,
        ),
    ],
    "edges": [
        _edge("e1", "mention_trigger", "thank_you_reply"),
    ],
}

# ---------------------------------------------------------------------------
# Component 16: Instagram - Hide a Comment
# ---------------------------------------------------------------------------

_INSTAGRAM_HIDE_SPAM_COMMENT_FRAGMENT = {
    "nodes": [
        _node(
            "hide_comment",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "hide_comment",
                "params": {"comment_id": "{{trigger.comment_id}}", "hidden": True},
            },
            "Hide the comment",
            0,
        ),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 17: Instagram - Delete a Comment
# ---------------------------------------------------------------------------

_INSTAGRAM_DELETE_COMMENT_FRAGMENT = {
    "nodes": [
        _node(
            "delete_comment",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "delete_comment",
                "params": {"comment_id": "{{trigger.comment_id}}"},
            },
            "Delete the comment",
            0,
        ),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 18: Instagram - Comment Moderation Combo
# ---------------------------------------------------------------------------
# `spam_gate`'s "false" handle is left unwired on purpose, same convention
# `_COUPON_CODE_CHECK_FRAGMENT`'s `check_coupon` node already establishes -
# wire it to wherever your workflow already handles a normal (non-spam)
# comment.

_INSTAGRAM_COMMENT_MODERATION_COMBO_FRAGMENT = {
    "nodes": [
        _node(
            "spam_gate",
            "condition",
            "condition.field_compare",
            {"field_path": "trigger.text", "operator": "contains", "value": "spam"},
            "Does the comment look like spam? (replace keyword)",
            0,
        ),
        _node(
            "hide_spam_comment",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "hide_comment",
                "params": {"comment_id": "{{trigger.comment_id}}", "hidden": True},
            },
            "Hide it",
            280,
        ),
    ],
    "edges": [
        _edge("e1", "spam_gate", "hide_spam_comment", source_handle="true"),
        # `spam_gate`'s "false" handle is left unwired on purpose - wire it
        # to whatever your workflow already does with a normal comment.
    ],
}

# ---------------------------------------------------------------------------
# Component 19: Instagram - Keyword Match Gate
# ---------------------------------------------------------------------------
# Both "true"/"false" handles are left unwired on purpose - a pure branch
# point for the author to drop into their own graph and wire both ways.

_INSTAGRAM_KEYWORD_MATCH_GATE_FRAGMENT = {
    "nodes": [
        _node(
            "keyword_gate",
            "condition",
            "condition.field_compare",
            {"field_path": "trigger.text", "operator": "contains", "value": "REPLACE_WITH_YOUR_KEYWORD"},
            "Does the text contain your keyword? (replace value)",
            0,
        ),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 20: Instagram - Post/Reel Scope Gate
# ---------------------------------------------------------------------------
# Same dangling-both-handles shape as the keyword gate above, scoped to
# `instagram.comment_received`'s `media_id` field instead of `text`.

_INSTAGRAM_POST_SCOPE_GATE_FRAGMENT = {
    "nodes": [
        _node(
            "post_scope_gate",
            "condition",
            "condition.field_compare",
            {"field_path": "trigger.media_id", "operator": "eq", "value": "REPLACE_WITH_YOUR_MEDIA_ID"},
            "Is this comment on the specific post/reel? (replace value)",
            0,
        ),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 21: Instagram - Wait Before Replying
# ---------------------------------------------------------------------------
# Generic `flow.delay`, not Instagram-specific under the hood, but heavily
# requested for pacing an Instagram auto-reply so it doesn't look instant.

_INSTAGRAM_WAIT_BEFORE_REPLYING_FRAGMENT = {
    "nodes": [
        _node("wait_before_reply", "action", "flow.delay", {"minutes": 5}, "Wait 5 minutes", 0),
    ],
    "edges": [],
}

# ---------------------------------------------------------------------------
# Component 22: Instagram - Escalate to a Human
# ---------------------------------------------------------------------------
# `pause_for_human`'s `auto_resume_after_hours` gives automation a chance
# to pick back up on its own if no agent gets to the conversation - `None`
# would mean "stays paused until an agent manually resumes it" instead, see
# `inbox_pause_automation.py`'s docstring.

_INSTAGRAM_ESCALATE_TO_HUMAN_FRAGMENT = {
    "nodes": [
        _node(
            "ack_reaction",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "react_to_message",
                "params": {
                    "recipient_id": "{{trigger.from}}",
                    "message_id": "{{trigger.message_id}}",
                    "reaction": "love",
                },
            },
            "Acknowledge with a reaction",
            0,
        ),
        _node(
            "ack_dm",
            "action",
            "connector.action",
            {
                "connector_instance_id": _PLACEHOLDER_CONNECTOR_ID,
                "action": "send_direct_message",
                "params": {
                    "recipient_id": "{{trigger.from}}",
                    "text": "Thanks for reaching out - one of our team members will follow up with you shortly!",
                },
            },
            "Send an acknowledgement DM",
            280,
        ),
        _node(
            "pause_for_human",
            "action",
            "inbox.pause_automation",
            {"connector_instance_id": _PLACEHOLDER_CONNECTOR_ID, "auto_resume_after_hours": 4},
            "Pause automation for a human (auto-resumes after 4h)",
            560,
        ),
    ],
    "edges": [
        _edge("e1", "ack_reaction", "ack_dm"),
        _edge("e2", "ack_dm", "pause_for_human"),
    ],
}

# ---------------------------------------------------------------------------
# Component 23: Instagram - Capture a Lead from a DM
# ---------------------------------------------------------------------------
# `records.upsert`'s `operation` is only ever "create" or "update" (no
# match-and-upsert-by-field mode exists on this node type - see
# `record_upsert.py::RecordUpsertConfig`), so this creates a fresh
# `customers` record every time it runs rather than deduping by
# `external_ref`; an author who wants dedup can add their own
# `records.query` lookup in front of this node.

_INSTAGRAM_CAPTURE_LEAD_FROM_DM_FRAGMENT = {
    "nodes": [
        _node(
            "capture_lead",
            "action",
            "records.upsert",
            {
                "module": "customers",
                "operation": "create",
                "fields": {
                    "external_ref": "{{trigger.from}}",
                    "name": "Instagram lead {{trigger.from}}",
                    "custom_fields": {"source": "instagram_dm", "last_message": "{{trigger.text}}"},
                },
            },
            "Save as a customer lead (replace the placeholder name)",
            0,
        ),
    ],
    "edges": [],
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
    {
        "key": "instagram_reply_to_comment",
        "name": "Instagram: Reply to Comment",
        "description": "Replies to an Instagram comment with your own text - wire your own trigger or keyword "
        "condition into this node.",
        "category": "Instagram",
        "icon": "reply",
        "graph_fragment": _INSTAGRAM_REPLY_TO_COMMENT_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_private_reply_to_comment",
        "name": "Instagram: Private Reply to Comment",
        "description": "Sends a private direct message to whoever left a comment, even if they've never messaged "
        "you before.",
        "category": "Instagram",
        "icon": "send",
        "graph_fragment": _INSTAGRAM_PRIVATE_REPLY_TO_COMMENT_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_reply_to_dm",
        "name": "Instagram: Reply to Direct Message",
        "description": "Sends a direct message back to whoever messaged your Instagram account.",
        "category": "Instagram",
        "icon": "message-circle",
        "graph_fragment": _INSTAGRAM_REPLY_TO_DM_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_react_to_message",
        "name": "Instagram: React to Message",
        "description": "Reacts to an inbound Instagram message with a heart - a quick way to acknowledge it before "
        "replying.",
        "category": "Instagram",
        "icon": "heart",
        "graph_fragment": _INSTAGRAM_REACT_TO_MESSAGE_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_send_media_reply",
        "name": "Instagram: Send a Media Reply",
        "description": "Sends an image (or video) as a direct message reply - replace the placeholder link with "
        "your own media.",
        "category": "Instagram",
        "icon": "image",
        "graph_fragment": _INSTAGRAM_SEND_MEDIA_REPLY_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_send_button_menu",
        "name": "Instagram: Send a Button Menu",
        "description": "Sends a short menu of tappable buttons so the customer can choose what they need next.",
        "category": "Instagram",
        "icon": "list",
        "graph_fragment": _INSTAGRAM_SEND_BUTTON_MENU_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_thank_story_reply",
        "name": "Instagram: Thank a Story Reply",
        "description": "Fires when someone replies to your Story and sends them a thank-you direct message.",
        "category": "Instagram",
        "icon": "heart-handshake",
        "graph_fragment": _INSTAGRAM_THANK_STORY_REPLY_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_thank_mention",
        "name": "Instagram: Thank a Mention",
        "description": "Fires when someone @mentions your account in a comment and thanks them with a reply.",
        "category": "Instagram",
        "icon": "at-sign",
        "graph_fragment": _INSTAGRAM_THANK_MENTION_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_hide_spam_comment",
        "name": "Instagram: Hide a Comment",
        "description": "Hides a comment from public view without deleting it - reversible, and still visible to "
        "its own author.",
        "category": "Instagram",
        "icon": "eye-off",
        "graph_fragment": _INSTAGRAM_HIDE_SPAM_COMMENT_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_delete_comment",
        "name": "Instagram: Delete a Comment",
        "description": "Permanently deletes a comment - use this instead of hiding it when it needs to be removed "
        "outright.",
        "category": "Instagram",
        "icon": "trash-2",
        "graph_fragment": _INSTAGRAM_DELETE_COMMENT_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_comment_moderation_combo",
        "name": "Instagram: Comment Moderation Combo",
        "description": "Checks a comment's text for a spam keyword and hides it automatically when it matches - "
        "wire the non-matching path into your normal comment flow.",
        "category": "Instagram",
        "icon": "filter",
        "graph_fragment": _INSTAGRAM_COMMENT_MODERATION_COMBO_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_keyword_match_gate",
        "name": "Instagram: Keyword Match Gate",
        "description": "Checks incoming text against a keyword you choose, ready to branch your workflow on a "
        "match.",
        "category": "Instagram",
        "icon": "filter",
        "graph_fragment": _INSTAGRAM_KEYWORD_MATCH_GATE_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_post_scope_gate",
        "name": "Instagram: Post/Reel Scope Gate",
        "description": "Checks which specific post or reel a comment was left on, so you can scope an automation "
        "to just that one.",
        "category": "Instagram",
        "icon": "image",
        "graph_fragment": _INSTAGRAM_POST_SCOPE_GATE_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_wait_before_replying",
        "name": "Instagram: Wait Before Replying",
        "description": "Pauses for 5 minutes before continuing, so an automated reply doesn't feel instant.",
        "category": "Instagram",
        "icon": "clock",
        "graph_fragment": _INSTAGRAM_WAIT_BEFORE_REPLYING_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_escalate_to_human",
        "name": "Instagram: Escalate to a Human",
        "description": "Acknowledges the customer, lets them know a person is taking over, and pauses automation "
        "on this conversation for 4 hours.",
        "category": "Instagram",
        "icon": "user-check",
        "graph_fragment": _INSTAGRAM_ESCALATE_TO_HUMAN_FRAGMENT,
        "required_object_types": None,
        "is_active": True,
    },
    {
        "key": "instagram_capture_lead_from_dm",
        "name": "Instagram: Capture a Lead from a DM",
        "description": "Saves the DM sender as a new customer record, so an interested follower doesn't get lost.",
        "category": "Instagram",
        "icon": "user-plus",
        "graph_fragment": _INSTAGRAM_CAPTURE_LEAD_FROM_DM_FRAGMENT,
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
